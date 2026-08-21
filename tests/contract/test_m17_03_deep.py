"""Deep M17-03 contract, runtime, replay, interface, and adversarial tests."""

# ruff: noqa: ARG002, E501, PLR2004, TC003, TRY003

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from evals.m17_03.run import _contribution, _evidence, build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import m1703 as adapter
from glio_proteogen.adapters.m1703 import app, m1703_app
from glio_proteogen.contracts.m17_03 import (
    DisagreementRecord,
    DisagreementStatus,
    IntegratedEvidenceObject,
    ReliabilityBand,
    SourceContribution,
    SourceKind,
    VariantPeptideIntegratedEvidenceResult,
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
    assert healthy.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert healthy.uncertainty.transport.probability is None
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
    with pytest.raises(ValueError, match="low reliability"):
        SourceContribution.model_validate(
            source.model_copy(
                update={"reliability_band": ReliabilityBand.LOW, "reliability_score": 0.6}
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
    with pytest.raises(ValueError, match="unresolved disagreement"):
        DisagreementRecord(
            disagreement_id="disagreement.bad-resolution",
            source_ids=("source-1", "source-2"),
            description="Unexpected resolution.",
            status=DisagreementStatus.OPEN,
            resolution="Must not be present.",
            evidence=(_evidence("bad-resolution-2"),),
        )
    with pytest.raises(ValueError, match="source ids"):
        DisagreementRecord(
            disagreement_id="disagreement.duplicate-sources",
            source_ids=("source-1", "source-1"),
            description="Duplicate source reference.",
            status=DisagreementStatus.OPEN,
            evidence=(_evidence("duplicate-sources"),),
        )


def test_object_request_and_result_closures_cover_duplicate_and_safe_failure_paths() -> None:
    engine = M1703FusionAggregationEngine()
    request = build_scenario_request()
    integrated = engine.infer(request).integrated_evidence
    assert integrated is not None
    with pytest.raises(ValueError, match="contribution ids"):
        IntegratedEvidenceObject.model_validate(
            integrated.model_copy(update={"contributions": integrated.contributions * 2}),
            strict=True,
        )
    disagreement = engine.infer(build_scenario_request("disagreement")).integrated_evidence
    assert disagreement is not None
    with pytest.raises(ValueError, match="disagreement ids"):
        IntegratedEvidenceObject.model_validate(
            disagreement.model_copy(update={"disagreements": disagreement.disagreements * 2}),
            strict=True,
        )
    with pytest.raises(ValueError, match="propagation ids"):
        IntegratedEvidenceObject.model_validate(
            integrated.model_copy(update={"propagation": integrated.propagation * 2}),
            strict=True,
        )
    with pytest.raises(ValueError, match="configuration version"):
        IntegratedEvidenceObject.model_validate(
            integrated.model_copy(update={"version": "9.9.9"}), strict=True
        )
    with pytest.raises(ValueError, match="unknown source"):
        IntegratedEvidenceObject.model_validate(
            integrated.model_copy(
                update={
                    "disagreements": (
                        disagreement.disagreements[0].model_copy(
                            update={"source_ids": ("source.unknown", "source-2")}
                        ),
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="unknown source"):
        IntegratedEvidenceObject.model_validate(
            integrated.model_copy(
                update={
                    "propagation": (
                        integrated.propagation[0].model_copy(update={"source_id": "source.unknown"}),
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="alignment"):
        type(request).model_validate(
            request.model_copy(
                update={
                    "alignment_result": request.source_artifacts[1],
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="source contribution ids"):
        type(request).model_validate(
            request.model_copy(update={"contributions": request.contributions[:1] * 2}),
            strict=True,
        )
    disagreement_request = build_scenario_request("disagreement")
    with pytest.raises(ValueError, match="unknown source"):
        type(request).model_validate(
            disagreement_request.model_copy(
                update={
                    "disagreements": (
                        disagreement_request.disagreements[0].model_copy(
                            update={"source_ids": ("source.unknown", "source-2")}
                        ),
                    )
                }
            ),
            strict=True,
        )
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
    with pytest.raises(ValueError, match="configuration version"):
        type(request).model_validate(
            request.model_copy(
                update={
                    "configuration": request.configuration.model_copy(update={"version": "9.9.9"})
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="request digest"):
        VariantPeptideIntegratedEvidenceResult.model_validate(
            engine.infer(request).model_copy(update={"request_digest": "sha256:" + "0" * 64}),
            strict=True,
        )
    low = engine.infer(build_scenario_request("low_reliability"))
    assert low.findings
    duplicate_finding = low.findings[0].model_copy(deep=True)
    with pytest.raises(ValueError, match="finding ids"):
        VariantPeptideIntegratedEvidenceResult.model_validate(
            low.model_copy(update={"findings": (duplicate_finding, duplicate_finding)}), strict=True
        )
    with pytest.raises(ValueError, match="supported attributable"):
        VariantPeptideIntegratedEvidenceResult.model_validate(
            engine.infer(request).model_copy(
                update={"support_decision": engine.infer(request).support_decision.model_copy(update={"status": SupportStatus.UNSUPPORTED})}
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="open disagreement"):
        VariantPeptideIntegratedEvidenceResult.model_validate(
            engine.infer(build_scenario_request("disagreement")).model_copy(
                update={"human_review_required": False}
            ),
            strict=True,
        )
    unsupported = engine.infer(build_scenario_request("unsupported"))
    with pytest.raises(ValueError, match="no integrated object"):
        VariantPeptideIntegratedEvidenceResult.model_validate(
            unsupported.model_copy(update={"integrated_evidence": integrated}), strict=True
        )
    with pytest.raises(ValueError, match="human review"):
        VariantPeptideIntegratedEvidenceResult.model_validate(
            unsupported.model_copy(update={"human_review_required": False}), strict=True
        )
    digest_payload = engine.infer(request)
    forged = digest_payload.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="result digest"):
        VariantPeptideIntegratedEvidenceResult.model_validate(forged, strict=True)


def test_request_duplicate_and_plugin_service_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = build_scenario_request()
    service = M1703Service()
    assert service.execute(canonical_json_bytes(request)).status.value == "integrated"
    plugin = M1703Plugin(service)
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1703Request", []))
    client = TestClient(app)
    payload = request.model_dump(mode="json")
    invalid = dict(payload)
    invalid.pop("contributions")
    assert client.post("/v1/modules/M17-03/fuse", json=invalid).status_code == 422
    assert client.post("/v1/modules/M17-03/verify", content=b"{}", headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/v1/modules/M17-03/verify", json={}).status_code == 422
    class DenyEngine:
        def infer(self, request: object) -> object:
            raise M1703AuthorizationError

    monkeypatch.setattr(adapter._SERVICE, "_engine", DenyEngine())
    assert client.post("/v1/modules/M17-03/fuse", json=request.model_dump(mode="json")).status_code == 403
    runner = CliRunner()
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    assert runner.invoke(m1703_app, ["fuse", str(malformed)]).exit_code != 0
    assert runner.invoke(m1703_app, ["verify", str(malformed)]).exit_code != 0
    assert runner.invoke(m1703_app, ["fuse", str(tmp_path / "missing.json")]).exit_code != 0


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
    assert runner.invoke(m1703_app, ["fuse", str(request_path)]).exit_code == 0
    assert runner.invoke(m1703_app, ["fuse", str(request_path), "--output", str(output_path)]).exit_code == 0
    assert runner.invoke(m1703_app, ["fuse", str(request_path), "--output", str(output_path)]).exit_code != 0
    assert runner.invoke(m1703_app, ["verify", str(output_path)]).exit_code == 0
