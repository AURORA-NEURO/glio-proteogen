"""Focused schema and completeness smoke for provisional M08-08."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m08_08 import (
    M0808_CALIBRATION_MEDIA_TYPE,
    M0808_OUTPUT_MEDIA_TYPE,
    M0808_UNCERTAINTY_MEDIA_TYPE,
    EvidenceBundle,
    EvidenceRole,
    ExplanationAssumption,
    PublishedEvidenceItem,
    PublisherDiagnosticStatus,
    ReconstructionStatus,
    ReconstructionStep,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_DIGEST = "sha256:" + ("a" * 64)


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def test_schema_inventory_is_strict_and_complete() -> None:
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
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["sourcesRequired"] is True
        assert metadata["assumptionsRequired"] is True
        assert metadata["counterEvidenceRequired"] is True
        assert metadata["reconstructionRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    output_meta = schemas["output"]["x-glio-contract"]
    assert output_meta["outputMediaType"] == M0808_OUTPUT_MEDIA_TYPE
    assert output_meta["calibrationInputMediaType"] == M0808_CALIBRATION_MEDIA_TYPE
    assert output_meta["uncertaintyInputMediaType"] == M0808_UNCERTAINTY_MEDIA_TYPE


def test_evidence_bundle_requires_counter_evidence_and_reconstruction() -> None:
    source = PublishedEvidenceItem(
        evidence_id="evidence.input",
        role=EvidenceRole.INPUT,
        artifact=_artifact("artifact.input"),
        claim="Input artifact is included for reconstruction.",
    )
    counter = PublishedEvidenceItem(
        evidence_id="evidence.counter",
        role=EvidenceRole.COUNTER_EVIDENCE,
        artifact=_artifact("artifact.counter"),
        claim="Counter-evidence is explicitly represented.",
    )
    bundle = EvidenceBundle(
        bundle_id="bundle.m0808.smoke",
        version="0.1.0",
        items=(source,),
        assumptions=(
            ExplanationAssumption(
                assumption_id="assumption.input",
                statement="The caller-declared input artifact is available.",
                evidence_ids=(source.evidence_id,),
            ),
        ),
        counter_evidence=(counter,),
        reconstruction=(
            ReconstructionStep(
                sequence=1,
                operation="publish-evidence",
                input_digests=(_DIGEST,),
                output_digest=_DIGEST,
                status=ReconstructionStatus.COMPLETE,
                evidence_ids=(source.evidence_id,),
            ),
        ),
    )
    assert bundle.counter_evidence[0].role is EvidenceRole.COUNTER_EVIDENCE
    assert bundle.reconstruction[0].status is ReconstructionStatus.COMPLETE
    assert PublisherDiagnosticStatus.WARNING.value == "warning"
