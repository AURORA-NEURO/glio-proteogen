"""Adversarial invariant coverage for M10-08 contract and runtime closure."""

import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m10_08.v1 import (
    ProteinRnaEvidenceBundle,
    ProteinRnaEvidencePublicationResult,
    ProteinRnaExplanation,
    PublishProteinRnaEvidenceRequest,
    ReconstructionStatus,
)
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c10_pathway_proteotype_factors import (
    m10_08_evidence_explanation_publisher as m1008_runtime,
)
from tests.modules.c10_pathway_proteotype_factors.test_m10_08_runtime import (
    _artifact,
    _request,
)


def _json_with(model: BaseModel, **updates: Any) -> str:
    payload = model.model_dump(mode="json")
    payload.update(updates)
    return json.dumps(payload)


def test_bundle_contract_rejects_every_structural_closure_violation() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request())
    assert result.bundle is not None
    bundle = result.bundle
    cases = [
        {"upstream_result": _artifact("wrong", "application/json").model_dump(mode="json")},
        {
            "sources": [
                *[item.model_dump(mode="json") for item in bundle.sources[:-1]],
                bundle.sources[-1]
                .model_copy(update={"source_id": bundle.sources[0].source_id})
                .model_dump(mode="json"),
            ]
        },
        {
            "sources": [
                *[item.model_dump(mode="json") for item in bundle.sources[:-1]],
                bundle.sources[-1]
                .model_copy(update={"artifact": bundle.sources[0].artifact})
                .model_dump(mode="json"),
            ]
        },
        {
            "reconstruction_steps": [
                bundle.reconstruction_steps[0]
                .model_copy(update={"sequence": 2})
                .model_dump(mode="json"),
                bundle.reconstruction_steps[0].model_dump(mode="json"),
            ]
        },
        {"reconstruction_status": ReconstructionStatus.PARTIAL.value},
    ]
    for case in cases:
        with pytest.raises(ValidationError):
            ProteinRnaEvidenceBundle.model_validate_json(_json_with(bundle, **case), strict=True)


def test_request_contract_rejects_media_duplicate_and_order_errors() -> None:
    request = _request()
    cases = [
        {"upstream_result": _artifact("wrong", "application/json").model_dump(mode="json")},
        {
            "source_artifacts": [
                request.source_artifacts[0].model_dump(mode="json"),
                request.source_artifacts[0].model_dump(mode="json"),
            ]
        },
        {
            "source_artifacts": [
                *[item.model_dump(mode="json") for item in request.source_artifacts[:-1]],
                request.source_artifacts[-1]
                .model_copy(update={"artifact": request.source_artifacts[0].artifact})
                .model_dump(mode="json"),
            ]
        },
        {
            "reconstruction_steps": [
                request.reconstruction_steps[0]
                .model_copy(update={"sequence": 2})
                .model_dump(mode="json"),
                request.reconstruction_steps[0].model_dump(mode="json"),
            ]
        },
    ]
    for case in cases:
        with pytest.raises(ValidationError):
            PublishProteinRnaEvidenceRequest.model_validate_json(
                _json_with(request, **case), strict=True
            )


def test_explanation_and_result_contracts_reject_closed_envelope_tampering() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request())
    assert result.explanation is not None
    explanation = result.explanation
    duplicate_diagnostic = explanation.diagnostics[0].model_dump(mode="json")
    with pytest.raises(ValidationError):
        ProteinRnaExplanation.model_validate_json(
            _json_with(
                explanation,
                diagnostics=[duplicate_diagnostic, duplicate_diagnostic],
            ),
            strict=True,
        )
    cases = [
        {"request_digest": "sha256:" + ("b" * 64)},
        {"result_id": "result.m1008.bad"},
        {"bundle": None},
        {"explanation": None},
        {"abstention_reason": "unexpected"},
        {
            "support_decision": {
                **result.support_decision.model_dump(mode="json"),
                "status": "limited",
            }
        },
        {
            "explanation": {
                **explanation.model_dump(mode="json"),
                "bundle_id": "bundle.m1008.other",
            }
        },
    ]
    for case in cases:
        with pytest.raises(ValidationError):
            ProteinRnaEvidencePublicationResult.model_validate_json(
                _json_with(result, **case), strict=True
            )


def test_abstained_result_contract_rejects_bundle_explanation_support_and_review_errors() -> None:
    result = m1008_runtime.publish_protein_rna_evidence(_request(complete=False))
    cases = [
        {
            "bundle": m1008_runtime.publish_protein_rna_evidence(_request()).bundle.model_dump(
                mode="json"
            )
        },
        {
            "explanation": m1008_runtime.publish_protein_rna_evidence(
                _request()
            ).explanation.model_dump(mode="json")
        },
        {"abstention_reason": None},
        {
            "support_decision": {
                **result.support_decision.model_dump(mode="json"),
                "status": "supported",
            }
        },
        {"human_review_required": False},
        {
            "provenance": {
                **result.provenance.model_dump(mode="json"),
                "module_id": "GLIO-PROTEOGEN-M01-01",
            }
        },
        {"provenance": {**result.provenance.model_dump(mode="json"), "consent_state": "withheld"}},
        {"findings": ["provisional_abi_pending_review", "provisional_abi_pending_review"]},
    ]
    for case in cases:
        with pytest.raises(ValidationError):
            ProteinRnaEvidencePublicationResult.model_validate_json(
                _json_with(result, **case), strict=True
            )


def test_runtime_validation_and_preflight_fail_closed_for_hostile_shapes() -> None:
    request = _request()
    with pytest.raises(PermissionError):
        m1008_runtime.preflight_m1008_authorization(object())
    with pytest.raises(PermissionError):
        m1008_runtime.preflight_m1008_authorization(
            {"context": {"references": {"support": {"state": 1}}}}
        )
    service = m1008_runtime.M1008EvidencePublisherService()

    class Candidate(BaseModel):
        context: object

    with pytest.raises(TypeError):
        service.validate_request(Candidate(context=request.context))
    with pytest.raises(ValueError, match="does not match"):
        service.validate_request({"context": request.context.model_dump(mode="json")})
    with pytest.raises(TypeError):
        m1008_runtime.M1008EvidencePublisherPlugin(service).run(object())  # type: ignore[arg-type]
    assert not m1008_runtime.verify_publication_result(object())
    assert not m1008_runtime.verify_publication_result({"result_digest": "sha256:" + ("a" * 64)})


def test_runtime_closure_reports_missing_sources_and_evidence_independently() -> None:
    request = _request()
    missing_kind = request.model_copy(update={"source_artifacts": request.source_artifacts[:1]})
    missing_evidence = request.model_copy(
        update={
            "source_artifacts": tuple(
                item.model_copy(update={"evidence": ()}) for item in request.source_artifacts
            )
        }
    )
    assert m1008_runtime.publish_protein_rna_evidence(missing_kind).bundle is None
    assert m1008_runtime.publish_protein_rna_evidence(missing_evidence).bundle is None


def test_plugin_typed_path_descriptor_and_json_validation_paths() -> None:
    service = m1008_runtime.M1008EvidencePublisherService()
    plugin = m1008_runtime.M1008EvidencePublisherPlugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M10-08"
    typed = plugin.validate(_request())
    assert plugin.run(typed).result_id.startswith("result.m1008.")
    invalid_payload = json.loads(_request().model_dump_json())
    invalid_payload.pop("source_artifacts")
    with pytest.raises(ValueError, match="does not match"):
        plugin.validate(json.dumps(invalid_payload))
    rejected = _request().model_copy(
        update={
            "context": _request().context.model_copy(
                update={
                    "references": _request().context.references.model_copy(
                        update={
                            "support": _request().context.references.support.model_copy(
                                update={"state": UpstreamDecisionState.REJECTED}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(PermissionError):
        plugin.validate(rejected.model_dump_json())
