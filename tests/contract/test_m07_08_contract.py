"""Focused contract/schema smoke for provisional M07-08."""

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m07_08 import (
    M0708_MAX_EVIDENCE,
    M0708_OUTPUT_MEDIA_TYPE,
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
    assert all(
        schema["x-glio-contract"]["reconstructionEvidenceRequiredForPublication"]
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0708_OUTPUT_MEDIA_TYPE
    assert M0708_MAX_EVIDENCE > 0


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


def test_schema_contracts_advertise_all_required_safety_boundaries() -> None:
    for schema in contract_json_schemas().values():
        metadata = schema["x-glio-contract"]
        assert metadata["abiStatus"] == "dossier-behavioral-brief-only"
        assert metadata["pendingOwnerConfirmation"] is True
        assert metadata["externalContentTraversal"] is False
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "proteotype"
        assert metadata["sourcesRequiredForPublication"] is True


def test_source_and_counter_roles_are_closed() -> None:
    with pytest.raises(ValidationError):
        PublisherEvidenceSource(
            source_id="source.role",
            kind=PublisherSourceKind.QUALITY_SUPPORT,
            artifact=ArtifactReference(
                artifact_id="artifact.role",
                version="1.0.0",
                digest="sha256:" + "b" * 64,
                media_type="application/json",
            ),
            claim="Opaque support artifact.",
            evidence=(
                {
                    "reference": {
                        "artifact_id": "artifact.role2",
                        "version": "1.0.0",
                        "digest": "sha256:" + "c" * 64,
                        "media_type": "application/json",
                    },
                    "role": "counter_evidence",
                    "claim": "invalid source role",
                },
            ),
        )
