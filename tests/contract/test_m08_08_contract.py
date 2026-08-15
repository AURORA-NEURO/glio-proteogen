"""Contract closure tests for the provisional M08-08 publisher ABI."""

# ruff: noqa: E501

from typing import cast

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m08_08 import (
    M0808_CALIBRATION_MEDIA_TYPE,
    M0808_UNCERTAINTY_MEDIA_TYPE,
    EvidenceBundle,
    EvidenceRole,
    ExplanationAssumption,
    ExplanationDiagnostic,
    ExplanationObject,
    PublishedEvidenceItem,
    PublisherDiagnosticStatus,
    PublisherReplayReason,
    PublisherStatus,
    PublishTranscriptProteinEvidenceRequest,
    PublishTranscriptProteinEvidenceResult,
    PublishTranscriptProteinEvidenceVerification,
    ReconstructionStatus,
    ReconstructionStep,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, SemanticVersion
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_08_evidence_explanation_publisher import (
    M0808EvidenceExplanationPublisher,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_08_publisher import _request

_D1 = "sha256:" + ("1" * 64)
_D2 = "sha256:" + ("2" * 64)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_D1 if name.endswith("1") else _D2,
        media_type=media_type,
    )


def _bundle() -> EvidenceBundle:
    items = (
        PublishedEvidenceItem(
            evidence_id="evidence.input.1",
            role=EvidenceRole.INPUT,
            artifact=_artifact("source.1"),
            claim="Source artifact is retained by content digest.",
        ),
        PublishedEvidenceItem(
            evidence_id="evidence.diagnostic.1",
            role=EvidenceRole.DIAGNOSTIC,
            artifact=_artifact("diagnostic.1"),
            claim="Diagnostic result is retained without relabeling.",
        ),
    )
    counter = PublishedEvidenceItem(
        evidence_id="evidence.counter.1",
        role=EvidenceRole.COUNTER_EVIDENCE,
        artifact=_artifact("counter.1"),
        claim="Discordant observation remains visible as counter-evidence.",
    )
    return EvidenceBundle(
        bundle_id="bundle.m08-08",
        version=cast("SemanticVersion", "0.1.0-provisional"),
        items=items,
        assumptions=(
            ExplanationAssumption(
                assumption_id="assumption.identity.1",
                statement="Caller-declared references identify the same analysis context.",
                evidence_ids=("evidence.input.1",),
            ),
        ),
        counter_evidence=(counter,),
        reconstruction=(
            ReconstructionStep(
                sequence=1,
                operation="bind source digests to the publisher projection",
                input_digests=(_D1,),
                output_digest=_D2,
                status=ReconstructionStatus.COMPLETE,
                evidence_ids=("evidence.input.1",),
            ),
        ),
    )


def test_schema_inventory_is_strict_and_dossier_scoped() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "bundle",
        "explanation",
        "evidence-item",
        "assumption",
        "diagnostic",
        "reconstruction-step",
        "verification",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["kinaseActivity"] is False
        assert metadata["allOmicsFusion"] is False
        assert metadata["treatmentRecommendation"] is False
        assert metadata["parentTarget"] == "protein_subtype"


def test_bundle_closure_rejects_unknown_reconstruction_and_assumption_links() -> None:
    with pytest.raises(ValueError, match="unknown evidence"):
        EvidenceBundle(
            bundle_id="bundle.bad",
            version="0.1.0-provisional",
            items=(
                PublishedEvidenceItem(
                    evidence_id="evidence.input.1",
                    role=EvidenceRole.INPUT,
                    artifact=_artifact("source.1"),
                    claim="source",
                ),
            ),
            assumptions=(
                ExplanationAssumption(
                    assumption_id="assumption.bad",
                    statement="bad link",
                    evidence_ids=("evidence.missing",),
                ),
            ),
            counter_evidence=(
                PublishedEvidenceItem(
                    evidence_id="evidence.counter.1",
                    role=EvidenceRole.COUNTER_EVIDENCE,
                    artifact=_artifact("counter.1"),
                    claim="counter",
                ),
            ),
            reconstruction=(
                ReconstructionStep(
                    sequence=1,
                    operation="replay",
                    input_digests=(_D1,),
                    output_digest=_D2,
                    status=ReconstructionStatus.COMPLETE,
                    evidence_ids=("evidence.input.1",),
                ),
            ),
        )


def test_bundle_and_explanation_are_immutable_and_id_closed() -> None:
    bundle = _bundle()
    assert bundle.counter_evidence[0].role is EvidenceRole.COUNTER_EVIDENCE
    with pytest.raises((TypeError, ValueError)):
        bundle.bundle_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="diagnostic ids"):
        ExplanationObject(
            explanation_id="explanation.1",
            version="0.1.0-provisional",
            summary="Summary",
            diagnostics=(
                ExplanationDiagnostic(
                    diagnostic_id="diagnostic.1",
                    status=PublisherDiagnosticStatus.PASS,
                    message="pass",
                ),
                ExplanationDiagnostic(
                    diagnostic_id="diagnostic.1",
                    status=PublisherDiagnosticStatus.WARNING,
                    message="duplicate",
                ),
            ),
            limitation_statements=("Provisional ABI.",),
            bundle_id=bundle.bundle_id,
        )


def test_upstream_media_types_are_explicit() -> None:
    calibration = _artifact("calibration.1", M0808_CALIBRATION_MEDIA_TYPE)
    uncertainty = _artifact("uncertainty.1", M0808_UNCERTAINTY_MEDIA_TYPE)
    assert calibration.media_type == M0808_CALIBRATION_MEDIA_TYPE
    assert uncertainty.media_type == M0808_UNCERTAINTY_MEDIA_TYPE


def test_replay_verification_closure_rejects_inconsistent_flags() -> None:
    with pytest.raises(ValueError, match="verified"):
        PublishTranscriptProteinEvidenceVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            reason=PublisherReplayReason.VERIFIED,
            result_digest=_D1,
        )
    with pytest.raises(ValueError, match="reason"):
        PublishTranscriptProteinEvidenceVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            reason=PublisherReplayReason.DIGEST_MISMATCH,
            result_digest=_D1,
        )
    with pytest.raises(ValueError, match="digest"):
        PublishTranscriptProteinEvidenceVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            reason=PublisherReplayReason.NON_CANONICAL,
            result_digest=_D1,
        )


def test_bundle_order_role_and_reference_closure() -> None:
    bundle = _bundle()
    with pytest.raises(ValueError, match="unique"):
        EvidenceBundle.bundle_is_closed(
            bundle.model_copy(
                update={
                    "items": (
                        bundle.items[0],
                        bundle.items[0].model_copy(update={"evidence_id": "evidence.counter.1"}),
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="assumption ids"):
        EvidenceBundle.bundle_is_closed(
            bundle.model_copy(
                update={
                    "assumptions": (
                        bundle.assumptions[0],
                        bundle.assumptions[0].model_copy(
                            update={"assumption_id": "assumption.identity.1"}
                        ),
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="assumption references"):
        EvidenceBundle.bundle_is_closed(
            bundle.model_copy(
                update={
                    "assumptions": (
                        bundle.assumptions[0].model_copy(update={"evidence_ids": ("missing",)}),
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="reconstruction references"):
        EvidenceBundle.bundle_is_closed(
            bundle.model_copy(
                update={
                    "reconstruction": (
                        bundle.reconstruction[0].model_copy(update={"evidence_ids": ("missing",)}),
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="ordered"):
        EvidenceBundle.bundle_is_closed(
            bundle.model_copy(
                update={
                    "reconstruction": (
                        bundle.reconstruction[0].model_copy(update={"sequence": 2}),
                        ReconstructionStep(
                            sequence=1,
                            operation="second",
                            input_digests=(_D1,),
                            output_digest=_D2,
                            status=ReconstructionStatus.COMPLETE,
                            evidence_ids=("evidence.input.1",),
                        ),
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="counter-evidence"):
        EvidenceBundle.bundle_is_closed(
            bundle.model_copy(
                update={
                    "counter_evidence": (
                        bundle.counter_evidence[0].model_copy(update={"role": EvidenceRole.INPUT}),
                    )
                }
            )
        )


def test_request_and_result_validator_branches_are_fail_closed() -> None:
    request = _request("source.1")
    assert canonical_request_digest(request.model_dump(mode="json")).startswith("sha256:")
    with pytest.raises(ValueError, match="M08-06"):
        PublishTranscriptProteinEvidenceRequest.request_is_bound(
            request.model_copy(
                update={"uncertainty_result": _artifact("uncertainty.2", "application/wrong")}
            )
        )
    with pytest.raises(ValueError, match="context"):
        PublishTranscriptProteinEvidenceRequest.request_is_bound(
            request.model_copy(
                update={
                    "context": request.context.model_copy(update={"request_id": "request.other"})
                }
            )
        )
    with pytest.raises(ValueError, match="distinct"):
        PublishTranscriptProteinEvidenceRequest.request_is_bound(
            request.model_copy(update={"source_artifacts": (request.calibration_result,)})
        )
    result = M0808EvidenceExplanationPublisher().publish(request).result
    forged_request = request.model_copy(
        update={"context": request.context.model_copy(update={"request_id": "request.other"})}
    )
    with pytest.raises(ValueError, match="context"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(
                update={
                    "request_digest": canonical_request_digest(forged_request),
                    "request": forged_request,
                }
            )
        )
    with pytest.raises(ValueError, match="source evidence"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(update={"evidence": ()})
        )
    with pytest.raises(ValueError, match="roles"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(
                update={"evidence": (result.evidence[0].model_copy(update={"role": "invalid"}),)}
            )
        )
    with pytest.raises(ValueError, match="complete supported evidence"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(update={"evidence_bundle": None, "explanation": None})
        )
    with pytest.raises(ValueError, match="counter-evidence"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(
                update={
                    "evidence_bundle": result.evidence_bundle.model_copy(
                        update={"counter_evidence": ()}
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="reconstruction"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(
                update={
                    "evidence_bundle": result.evidence_bundle.model_copy(
                        update={"reconstruction": ()}
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="diagnostics"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(
                update={"explanation": result.explanation.model_copy(update={"diagnostics": ()})}
            )
        )
    with pytest.raises(ValueError, match="abstained"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(
                update={"status": PublisherStatus.ABSTAINED, "abstention_reason": "review"}
            )
        )
    with pytest.raises(ValueError, match="digest"):
        PublishTranscriptProteinEvidenceResult.result_is_closed(
            result.model_copy(update={"result_digest": _D2})
        )
