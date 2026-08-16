"""Focused contract/schema smoke for provisional M10-08."""

from glio_proteogen.contracts.m10_08 import (
    M1008_MAX_EVIDENCE,
    M1008_OUTPUT_MEDIA_TYPE,
    M1008_PROVISIONAL_ABI,
    PublisherEvidenceSource,
    PublisherSourceKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_publication_evidence_fields() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["reconstructionEvidenceRequiredForPublication"]
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1008_OUTPUT_MEDIA_TYPE
    assert M1008_PROVISIONAL_ABI is True
    assert M1008_MAX_EVIDENCE > 0


def test_source_attribution_keeps_external_payload_opaque() -> None:
    source = PublisherEvidenceSource(
        source_id="source.ms",
        kind=PublisherSourceKind.MASS_SPECTROMETRY_PROTEOME,
        artifact=ArtifactReference(
            artifact_id="artifact.ms",
            version="1.0.0",
            digest="sha256:" + "a" * 64,
            media_type="application/octet-stream",
        ),
        claim="Mass-spectrometry proteome source; authority remains external.",
    )
    assert source.artifact.artifact_id == "artifact.ms"
    assert source.evidence == ()
