"""Focused contract/schema smoke for provisional M17-03."""

import pytest

from glio_proteogen.contracts.m17_03 import (
    M1703_OUTPUT_MEDIA_TYPE,
    M1703_PROVISIONAL_ABI,
    DisagreementRecord,
    DisagreementStatus,
    FusionConfiguration,
    IntegratedEvidenceObject,
    ReliabilityBand,
    SourceContribution,
    SourceKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 8


def _source(source_id: str, artifact_id: str) -> SourceContribution:
    return SourceContribution(
        source_id=source_id,
        kind=SourceKind.MASS_SPECTROMETRY_PROTEOME,
        artifact=ArtifactReference(
            artifact_id=artifact_id,
            version="0.1.0",
            media_type="application/octet-stream",
            digest="sha256:" + "a" * 64,
        ),
        claim="Attributable source claim.",
        reliability_score=0.8,
        reliability_band=ReliabilityBand.HIGH,
        uncertainty_note="Caller-declared uncertainty.",
        evidence=(
            EvidenceReference(
                reference=ArtifactReference(
                    artifact_id=f"evidence-{source_id}",
                    version="0.1.0",
                    media_type="application/octet-stream",
                    digest="sha256:" + "b" * 64,
                ),
                role="evidence",
                claim="Source evidence.",
            ),
        ),
    )


def test_provisional_schemas_preserve_attribution_and_conflicts() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["componentSpecificIntegration"]
        and schema["x-glio-contract"]["sourceAttributionRequired"]
        and schema["x-glio-contract"]["reliabilityRequired"]
        and schema["x-glio-contract"]["disagreementPreserved"]
        and schema["x-glio-contract"]["signedPropagationRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m17-02+json")
        and schema["x-glio-contract"]["parentTarget"] == "variant_peptide"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1703_OUTPUT_MEDIA_TYPE
    assert M1703_PROVISIONAL_ABI is True


def test_integrated_object_retains_source_identity_and_open_disagreement() -> None:
    first = _source("source-1", "artifact-1")
    second = _source("source-2", "artifact-2")
    disagreement = DisagreementRecord(
        disagreement_id="disagreement-1",
        source_ids=(first.source_id, second.source_id),
        description="Sources disagree on the integrated claim.",
        status=DisagreementStatus.OPEN,
        evidence=first.evidence,
    )
    integrated = IntegratedEvidenceObject(
        integrated_id="integrated-1",
        version="0.1.0",
        contributions=(first, second),
        disagreements=(disagreement,),
        configuration=FusionConfiguration(
            configuration_id="config-1",
            version="0.1.0",
            reliability_threshold=0.7,
            evidence=first.evidence,
        ),
        evidence=first.evidence,
    )
    assert tuple(item.source_id for item in integrated.contributions) == ("source-1", "source-2")
    assert integrated.disagreements[0].status is DisagreementStatus.OPEN
    with pytest.raises(ValueError, match="resolved disagreement requires"):
        DisagreementRecord(
            disagreement_id="bad-disagreement",
            source_ids=("source-1", "source-2"),
            description="Resolution is absent.",
            status=DisagreementStatus.RESOLVED,
            evidence=first.evidence,
        )
