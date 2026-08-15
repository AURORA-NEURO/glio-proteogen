"""Focused contract/schema smoke for provisional M26-08."""

from glio_proteogen.contracts.m26_08 import (
    M2608_OUTPUT_MEDIA_TYPE,
    M2608_PROVISIONAL_ABI,
    ArchiveStatus,
    EvidencePreservation,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 10


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=ArtifactReference(
            artifact_id="artifact-1",
            version="0.1.0",
            digest="sha256:" + "a" * 64,
            media_type="application/octet-stream",
        ),
        role="evidence",
        claim="Caller-declared retirement evidence.",
    )


def test_provisional_schemas_preserve_retirement_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["retirementCriteriaRequired"]
        and schema["x-glio-contract"]["dependencyMigrationRequired"]
        and schema["x-glio-contract"]["evidencePreservationRequired"]
        and schema["x-glio-contract"]["communicationRequired"]
        and schema["x-glio-contract"]["longTermArchiveRequired"]
        and schema["x-glio-contract"]["retrievableEvidenceRequired"]
        and schema["x-glio-contract"]["noActiveDependencies"]
        and schema["x-glio-contract"]["signedReleaseBundleFallback"]
        and schema["x-glio-contract"]["humanReviewRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2608_OUTPUT_MEDIA_TYPE
    assert M2608_PROVISIONAL_ABI is True


def test_evidence_preservation_requires_retrievable_checksum_verified_artifact() -> None:
    preservation = EvidencePreservation(
        preservation_id="preservation-1",
        artifact=ArtifactReference(
            artifact_id="archive-artifact",
            version="0.1.0",
            digest="sha256:" + "b" * 64,
            media_type="application/octet-stream",
        ),
        retention_class="long-term",
        retrievable=True,
        evidence=(_evidence(),),
    )
    assert preservation.checksum_verified is True
    assert preservation.retrievable is True
    assert ArchiveStatus.VERIFIED.value == "verified"
