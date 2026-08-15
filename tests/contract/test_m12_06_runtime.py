"""Adversarial contract, runtime, replay, and interface tests for M12-06."""

# Path is part of the Typer/pytest runtime signature; HTTP status literals keep
# the assertions directly readable in this focused adapter matrix.
# ruff: noqa: TC003,PLR2004,E501

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1206 import app, m1206_app
from glio_proteogen.contracts.m12_06 import (
    PerturbationKind,
    PerturbationPolicy,
    PerturbationScenario,
    PerturbationStatus,
    SimulateBiomarkerPanelPerturbationRequest,
    SimulatorConfiguration,
    SimulatorStatus,
    canonical_request_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator import (
    M1206AuthorizationError,
    M1206Plugin,
    M1206ReplayError,
    M1206Service,
)

_RUNNER = CliRunner()
_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _artifact(name: str, index: int = 1) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + f"{index:064x}",
        media_type="application/json",
    )


def _controls(*, denied: str | None = None) -> ContextReferences:
    accepted = (
        UpstreamDecisionState.REJECTED
        if denied
        in {
            "approved_configuration",
            "provenance",
            "quality",
            "support",
            "intended_use",
        }
        else UpstreamDecisionState.ACCEPTED
    )
    identity = (
        IdentityLineageState.CONFLICTED
        if denied == "identity_lineage"
        else IdentityLineageState.RESOLVED
    )
    consent = ConsentState.WITHHELD if denied == "consent" else ConsentState.GRANTED
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="config-decision",
            state=accepted,
            policy_version="1.0.0",
            evidence=_artifact("control.config", 10),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="identity-decision",
            state=identity,
            policy_version="1.0.0",
            binding_digest=_artifact("subject", 11).digest,
            evidence=_artifact("control.identity", 11),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="provenance-decision",
            state=accepted,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance", 12),
        ),
        consent=ConsentReference(
            decision_id="consent-decision",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent", 13),
        ),
        quality=UpstreamDecisionReference(
            decision_id="quality-decision",
            state=accepted,
            policy_version="1.0.0",
            evidence=_artifact("control.quality", 14),
        ),
        support=UpstreamDecisionReference(
            decision_id="support-decision",
            state=accepted,
            policy_version="1.0.0",
            evidence=_artifact("control.support", 15),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="intended-use-decision",
            state=accepted,
            policy_version="1.0.0",
            evidence=_artifact("control.use", 16),
        ),
    )


def _request(
    *,
    denied: str | None = None,
    scenario_status: PerturbationStatus = PerturbationStatus.SUPPORTED,
    value: float = 0.4,
) -> SimulateBiomarkerPanelPerturbationRequest:
    context = ExecutionContext(
        request_id="request-1",
        actor_id="actor-1",
        occurred_at=_NOW,
        references=_controls(denied=denied),
    )
    evidence = EvidenceReference(
        reference=_artifact("scenario.evidence", 22),
        role="evidence",
        claim="Scenario source is reviewed.",
    )
    scenario = PerturbationScenario(
        scenario_id="scenario-1",
        kind=PerturbationKind.PARAMETER_SWEEP,
        parameter="panel.signal",
        baseline_value=value,
        perturbed_value=value + 0.1,
        unit="relative",
        status=scenario_status,
        assumption="Panel response is locally bounded.",
        source_artifact=_artifact("scenario.source", 21),
        evidence=(evidence,) if scenario_status is PerturbationStatus.SUPPORTED else (),
    )
    config = SimulatorConfiguration(
        configuration_id="config-1",
        version="1.0.0",
        method="bounded-deterministic-reference",
        model_reference=_artifact("model", 30),
        units_reference=_artifact("units", 31),
        evidence=(evidence,),
    )
    return SimulateBiomarkerPanelPerturbationRequest(
        request_id="request-1",
        context=context,
        upstream_consequence_result=_artifact("upstream", 20),
        policy=PerturbationPolicy(
            maximum_scenarios=4,
            response_lower_bound=0.0,
            response_upper_bound=1.0,
            configuration=config,
        ),
        scenarios=(scenario,),
        source_artifacts=(_artifact("source", 23),),
    )


def test_supported_simulation_is_bounded_and_replayable() -> None:
    request = _request()
    result = M1206Service().execute(request)
    assert result.status is SimulatorStatus.SIMULATED
    assert result.sensitivity_surface is not None
    assert result.result_digest.startswith("sha256:")
    assert result.request_digest == canonical_request_digest(request)
    assert M1206Service().verify(request, result) == result


@pytest.mark.parametrize("denied", ["consent", "identity_lineage", "support", "quality"])
def test_denied_controls_are_rejected_before_execution(denied: str) -> None:
    with pytest.raises(M1206AuthorizationError):
        M1206Service().execute(_request(denied=denied))


def test_unsupported_scenario_abstains_without_surface() -> None:
    result = M1206Service().execute(_request(scenario_status=PerturbationStatus.UNSUPPORTED))
    assert result.status is SimulatorStatus.ABSTAINED
    assert result.sensitivity_surface is None
    assert result.human_review_required


def test_out_of_envelope_abstains() -> None:
    result = M1206Service().execute(_request(value=1.1))
    assert result.status is SimulatorStatus.ABSTAINED
    assert result.sensitivity_surface is None


def test_result_tamper_is_rejected() -> None:
    request = _request()
    result = M1206Service().execute(request)
    tampered = result.model_copy(update={"result_id": "tampered"})
    with pytest.raises((ValueError, M1206ReplayError)):
        M1206Service().verify(request, tampered)


def test_plugin_validates_once_and_rejects_unissued_token() -> None:
    request = _request()
    plugin = M1206Plugin(M1206Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M12-06"
    token = plugin.validate(request.model_dump_json())
    assert plugin.run(token).status is SimulatorStatus.SIMULATED
    with pytest.raises(TypeError):
        plugin.run(request)  # type: ignore[arg-type]


def test_fastapi_schema_and_simulate() -> None:
    client = TestClient(app)
    schema = client.get("/v1/m12-06/schema/request")
    assert schema.status_code == 200
    response = client.post("/v1/modules/M12-06/simulate", content=_request().model_dump_json())
    assert response.status_code == 200
    assert response.json()["status"] == "simulated"


def test_fastapi_sanitizes_duplicate_and_denied_requests() -> None:
    client = TestClient(app)
    duplicate = '{"request_id":"x","request_id":"y"}'
    response = client.post("/v1/modules/M12-06/simulate", content=duplicate)
    assert response.status_code == 400
    denied = client.post(
        "/v1/modules/M12-06/simulate", content=_request(denied="consent").model_dump_json()
    )
    assert denied.status_code == 403


def test_fastapi_verify_round_trip() -> None:
    client = TestClient(app)
    request = _request()
    result = M1206Service().execute(request)
    envelope = json.dumps(
        {"request": request.model_dump(mode="json"), "result": result.model_dump(mode="json")}
    )
    response = client.post("/v1/modules/M12-06/verify", content=envelope)
    assert response.status_code == 200


def test_cli_schema_and_no_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "schema.json"
    first = _RUNNER.invoke(m1206_app, ["export-schema", "request", "--output", str(output)])
    assert first.exit_code == 0
    second = _RUNNER.invoke(m1206_app, ["export-schema", "request", "--output", str(output)])
    assert second.exit_code != 0
    forced = _RUNNER.invoke(
        m1206_app, ["export-schema", "request", "--output", str(output), "--force"]
    )
    assert forced.exit_code == 0
    stdout_schema = _RUNNER.invoke(m1206_app, ["export-schema", "request"])
    assert stdout_schema.exit_code == 0
    unknown_schema = _RUNNER.invoke(m1206_app, ["export-schema", "unknown"])
    assert unknown_schema.exit_code != 0


def test_cli_simulate_and_verify_round_trip(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    simulated = _RUNNER.invoke(
        m1206_app, ["simulate", str(request_path), "--output", str(result_path)]
    )
    assert simulated.exit_code == 0
    verified = _RUNNER.invoke(m1206_app, ["verify", str(request_path), str(result_path)])
    assert verified.exit_code == 0
    stdout_simulated = _RUNNER.invoke(m1206_app, ["simulate", str(request_path)])
    assert stdout_simulated.exit_code == 0


def test_interfaces_reject_invalid_payloads() -> None:
    client = TestClient(app)
    invalid = client.post("/v1/modules/M12-06/simulate", content=b"{}")
    assert invalid.status_code == 403
    unknown_schema = client.get("/v1/m12-06/schema/unknown")
    assert unknown_schema.status_code == 404
    non_object_verify = client.post("/v1/modules/M12-06/verify", content=b"[]")
    assert non_object_verify.status_code == 422
    cli_invalid = _RUNNER.invoke(m1206_app, ["simulate", "does-not-exist.json"])
    assert cli_invalid.exit_code != 0


def test_interfaces_cover_validation_and_replay_errors(tmp_path: Path) -> None:
    client = TestClient(app)
    malformed = _request().model_dump(mode="json")
    malformed["request_id"] = 42
    malformed_response = client.post("/v1/modules/M12-06/simulate", content=json.dumps(malformed))
    assert malformed_response.status_code == 422
    request = _request()
    result = M1206Service().execute(request)
    changed_context = request.context.model_copy(update={"request_id": "request-2"})
    changed_request = request.model_copy(
        update={"request_id": "request-2", "context": changed_context}
    )
    envelope = json.dumps(
        {
            "request": changed_request.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
    )
    replay_response = client.post("/v1/modules/M12-06/verify", content=envelope)
    assert replay_response.status_code == 409
    denied_envelope = json.dumps(
        {
            "request": _request(denied="consent").model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
    )
    denied_response = client.post("/v1/modules/M12-06/verify", content=denied_envelope)
    assert denied_response.status_code == 403
    syntax_response = client.post("/v1/modules/M12-06/verify", content=b"{")
    assert syntax_response.status_code == 400
    request_path = tmp_path / "request.json"
    invalid_path = tmp_path / "invalid.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    invalid_path.write_text(json.dumps(malformed), encoding="utf-8")
    cli_malformed = _RUNNER.invoke(m1206_app, ["simulate", str(invalid_path)])
    assert cli_malformed.exit_code != 0
    result_path = tmp_path / "result.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")
    changed_path = tmp_path / "changed-request.json"
    changed_path.write_text(changed_request.model_dump_json(), encoding="utf-8")
    cli_replay = _RUNNER.invoke(m1206_app, ["verify", str(changed_path), str(result_path)])
    assert cli_replay.exit_code != 0
