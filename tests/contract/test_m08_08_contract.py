"""Contract closure tests for the provisional M08-08 publisher ABI."""

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
    ReconstructionStatus,
    ReconstructionStep,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, SemanticVersion

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
