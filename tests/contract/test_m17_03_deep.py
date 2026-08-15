"""Deep M17-03 contract, runtime, replay, interface, and adversarial tests."""

# ruff: noqa: E501, PLR2004, TC003, TRY003

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from evals.m17_03.run import _contribution, _evidence, build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1703 import app, m1703_app
from glio_proteogen.contracts.m17_03 import (
    DisagreementRecord,
    DisagreementStatus,
    ReliabilityBand,
    SourceContribution,
    SourceKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_03_fusion_aggregation_engine import (
    M1703AuthorizationError,
    M1703FusionAggregationEngine,
    M1703Plugin,
    M1703ReplayVerificationError,
    M1703Service,
    ValidatedM1703Request,
    fuse_variant_peptide_evidence,
    preflight_m1703_authorization,
)


def test_runtime_statuses_preserve_attribution_disagreement_and_abstention() -> None:
    engine = M1703FusionAggregationEngine()
    healthy = engine.infer(build_scenario_request())
    assert healthy.integrated_evidence is not None
    assert healthy.status.value == "integrated"
    assert healthy.support_decision.status is SupportStatus.SUPPORTED
    disagreement = engine.infer(build_scenario_request("disagreement"))
    assert disagreement.integrated_evidence is not None
    assert disagreement.integrated_evidence.disagreements[0].status is DisagreementStatus.OPEN
    assert disagreement.human_review_required
    assert disagreement.support_decision.status is SupportStatus.REVIEW_REQUIRED
    unsupported = engine.infer(build_scenario_request("unsupported"))
    assert unsupported.integrated_evidence is None
    assert unsupported.abstention_reason is not None
    assert unsupported.human_review_required
    assert unsupported.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_contract_reliability_and_reference_closures_are_adversarial() -> None:
    source = _contribution("source-x", SourceKind.GENOME, 0.8, ReliabilityBand.HIGH)
    with pytest.raises(ValueError, match="high reliability"):
        SourceContribution.model_validate(
            source.model_copy(update={"reliability_score": 0.2}), strict=True
        )
    with pytest.raises(ValueError, match="moderate reliability"):
        SourceContribution.model_validate(
            source.model_copy(
                update={"reliability_band": ReliabilityBand.MODERATE, "reliability_score": 0.9}
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="zero score"):
        SourceContribution.model_validate(
            source.model_copy(
                update={"reliability_band": ReliabilityBand.NOT_EVALUABLE, "reliability_score": 0.1}
            ),
            strict=True,
        )
    request = build_scenario_request()
    duplicate = request.model_dump(mode="python")
    duplicate["source_artifacts"] = request.source_artifacts + request.source_artifacts[:1]
    with pytest.raises(ValueError, match="source artifact"):
        type(request).model_validate(duplicate, strict=True)
    with pytest.raises(ValueError, match="unknown source"):
        type(request).model_validate(
            request.model_copy(
                update={
                    "propagation": (
                        request.propagation[0].model_copy(update={"source_id": "source.unknown"}),
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="resolution"):
        DisagreementRecord(
            disagreement_id="disagreement.bad",
            source_ids=("source-1", "source-2"),
            description="Missing resolution.",
            status=DisagreementStatus.RESOLVED,
            evidence=(_evidence("bad-resolution"),),
        )


def test_replay_service_plugin_and_public_operation_parity() -> None:
    request = build_scenario_request()
    engine = M1703FusionAggregationEngine()
    result = engine.infer(request)
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1703ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    service = M1703Service()
    plugin = M1703Plugin(service)
    token = plugin.validate(request)
    assert plugin.run(token).model_dump(mode="json") == service.execute(token.request).model_dump(mode="json")
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1703Request", request))
    with pytest.raises(TypeError):
        plugin.run(replace(token, _seal=object()))
    assert plugin.run(plugin.validate(canonical_json_bytes(request))).status.value == "integrated"
    assert plugin.verify(result).status.value == "integrated"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M17-03"
    assert fuse_variant_peptide_evidence(request).result_id == result.result_id


def test_authorization_preflight_is_fail_closed() -> None:
    with pytest.raises(M1703AuthorizationError):
        M1703FusionAggregationEngine().infer(build_scenario_request(accepted=False))

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1703AuthorizationError):
        preflight_m1703_authorization(Exploding())


def test_schemas_evaluator_and_interfaces_are_closed(tmp_path: Path) -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == 8
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["parentTarget"] == "variant_peptide" for schema in schemas.values())
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == report["executed_cases"] == 6
    client = TestClient(app)
    payload = build_scenario_request().model_dump(mode="json")
    assert client.get("/v1/m17-03/schema/request").status_code == 200
    assert client.get("/v1/m17-03/schema/unknown").status_code == 404
    response = client.post("/v1/modules/M17-03/fuse", json=payload)
    assert response.status_code == 200
    assert client.post("/v1/modules/M17-03/verify", json=response.json()).status_code == 200
    assert client.post("/v1/modules/M17-03/fuse", content=b"{", headers={"content-type": "application/json"}).status_code == 422
    assert client.post("/v1/modules/M17-03/fuse", json=build_scenario_request(accepted=False).model_dump(mode="json")).status_code == 403
    assert client.post("/v1/modules/M17-03/fuse", content=b"{}", headers={"content-type": "text/plain"}).status_code == 415
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1703_app, ["export-schema", "output"]).exit_code == 0
    assert runner.invoke(m1703_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(m1703_app, ["fuse", str(request_path), "--output", str(output_path)]).exit_code == 0
    assert runner.invoke(m1703_app, ["fuse", str(request_path), "--output", str(output_path)]).exit_code != 0
    assert runner.invoke(m1703_app, ["verify", str(output_path)]).exit_code == 0
