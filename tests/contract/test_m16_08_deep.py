"""Deep contract, runtime, interface, replay, and adversarial M16-08 coverage."""

# ruff: noqa: E501, PLR2004, TC003, TRY003

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from evals.m16_08.run import _signal, build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1608 import app, m1608_app
from glio_proteogen.contracts.m16_08 import (
    HealthSignalKind,
    HealthSignalStatus,
    MonitorDiagnosticStatus,
    MonitorProteinRnaTranslationHealthRequest,
    ProteinRnaDiscordanceTranslationHealthResult,
    RollbackDecision,
    TranslationHealthStatus,
    contract_json_schema,
    contract_json_schemas,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c16_protein_rna_discordance.m16_08_translation_monitoring_rollback import (
    M1608AuthorizationError,
    M1608Plugin,
    M1608ReplayVerificationError,
    M1608Service,
    M1608TranslationMonitoringEngine,
    ValidatedM1608Request,
    monitor_protein_rna_translation_health,
    preflight_m1608_authorization,
)


def test_schema_metadata_and_unknown_schema_are_closed() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {
        "request", "output", "report", "signal", "assessment", "rollback-plan", "configuration", "diagnostic"
    }
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["suspensionAndRollbackExplicit"] is True
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_runtime_statuses_and_provenance_are_explicit() -> None:
    engine = M1608TranslationMonitoringEngine()
    healthy = engine.infer(build_scenario_request())
    assert healthy.health_status is TranslationHealthStatus.HEALTHY
    assert healthy.rollback_decision is RollbackDecision.CONTINUE
    assert healthy.report is not None
    assert healthy.provenance.module_id == "GLIO-PROTEOGEN-M16-08"
    assert healthy.uncertainty.transport.probability == 0.9
    degraded = engine.infer(
        build_scenario_request(
            signals=(_signal("signal.support", HealthSignalKind.SUPPORT_DRIFT, "support proportion", 0.72, HealthSignalStatus.DRIFTING, 0.80, 1.0),)
        )
    )
    assert degraded.health_status is TranslationHealthStatus.DEGRADED
    assert degraded.rollback_decision is RollbackDecision.SUSPEND
    assert degraded.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert degraded.diagnostics[0].status is MonitorDiagnosticStatus.WARNING


def test_critical_rollback_and_unsupported_abstention() -> None:
    engine = M1608TranslationMonitoringEngine()
    critical = engine.infer(
        build_scenario_request(
            signals=(_signal("signal.discrepancy", HealthSignalKind.DISCREPANCY, "critical discrepancy count", 4.0, HealthSignalStatus.DRIFTING, 0.0, 1.0),)
        )
    )
    assert critical.health_status is TranslationHealthStatus.CRITICAL
    assert critical.rollback_decision is RollbackDecision.ROLLBACK
    assert critical.human_review_required
    unsupported = engine.infer(
        build_scenario_request(
            signals=(_signal("signal.unknown", HealthSignalKind.WORKFLOW_EFFECT, "workflow effect", 0.0, HealthSignalStatus.NOT_EVALUABLE, None, None),)
        )
    )
    assert unsupported.health_status is TranslationHealthStatus.ABSTAINED
    assert unsupported.report is None
    assert unsupported.rollback_decision is RollbackDecision.ABSTAIN
    assert unsupported.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert unsupported.human_review_required


def test_request_and_result_closures_reject_tamper() -> None:
    request = build_scenario_request()
    duplicate = request.model_dump(mode="python")
    duplicate["source_artifacts"] = request.source_artifacts + request.source_artifacts[:1]
    with pytest.raises(ValueError, match="source artifact"):
        MonitorProteinRnaTranslationHealthRequest.model_validate(duplicate, strict=True)
    result = M1608TranslationMonitoringEngine().infer(request)
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "0" * 64
    payload["result_digest"] = result_payload_digest(
        ProteinRnaDiscordanceTranslationHealthResult.model_construct(**payload)
    )
    with pytest.raises(ValueError, match="request digest"):
        ProteinRnaDiscordanceTranslationHealthResult.model_validate(payload, strict=True)


def test_authorization_plugin_service_and_replay_parity() -> None:
    with pytest.raises(M1608AuthorizationError):
        M1608TranslationMonitoringEngine().infer(build_scenario_request(accepted=False))

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1608AuthorizationError):
        preflight_m1608_authorization(Exploding())
    engine = M1608TranslationMonitoringEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1608ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    service = M1608Service()
    plugin = M1608Plugin(service)
    token = plugin.validate(build_scenario_request())
    assert plugin.run(token).model_dump(mode="json") == service.execute(token.request).model_dump(mode="json")
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1608Request", build_scenario_request()))
    json_token = plugin.validate(canonical_json_bytes(build_scenario_request()))
    assert plugin.run(json_token).health_status is TranslationHealthStatus.HEALTHY
    assert plugin.verify(result).health_status is TranslationHealthStatus.HEALTHY
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M16-08"
    assert monitor_protein_rna_translation_health(build_scenario_request()).health_status is TranslationHealthStatus.HEALTHY


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == report["executed_cases"] == 6


def test_fastapi_interfaces_and_sanitized_errors() -> None:
    client = TestClient(app)
    assert client.get("/v1/m16-08/schema/request").status_code == 200
    assert client.get("/v1/m16-08/schema/unknown").status_code == 404
    payload = build_scenario_request().model_dump(mode="json")
    response = client.post("/v1/modules/M16-08/monitor", json=payload)
    assert response.status_code == 200
    assert client.post("/v1/modules/M16-08/verify", json=response.json()).status_code == 200
    assert client.post(
        "/v1/modules/M16-08/monitor",
        json=build_scenario_request(accepted=False).model_dump(mode="json"),
    ).status_code == 403
    assert client.post(
        "/v1/modules/M16-08/monitor", content=b"{", headers={"content-type": "application/json"}
    ).status_code == 422
    invalid = dict(payload)
    invalid.pop("signals")
    assert client.post("/v1/modules/M16-08/monitor", json=invalid).status_code == 422
    assert client.post(
        "/v1/modules/M16-08/monitor", content=b"{}", headers={"content-type": "text/plain"}
    ).status_code == 415
    assert client.post("/v1/modules/M16-08/verify", json={}).status_code == 422
    assert client.post(
        "/v1/modules/M16-08/verify", content=b"{}", headers={"content-type": "text/plain"}
    ).status_code == 415


def test_cli_monitor_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1608_app, ["export-schema", "output"]).exit_code == 0
    assert runner.invoke(m1608_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(m1608_app, ["monitor", str(request_path), "--output", str(output_path)]).exit_code == 0
    assert runner.invoke(m1608_app, ["monitor", str(request_path), "--output", str(output_path)]).exit_code != 0
    assert runner.invoke(m1608_app, ["monitor", str(request_path)]).exit_code == 0
    assert runner.invoke(m1608_app, ["verify", str(output_path)]).exit_code == 0
