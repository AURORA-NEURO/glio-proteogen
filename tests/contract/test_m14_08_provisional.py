"""Focused schema and evidence-chain smoke for provisional M14-08."""

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m14_08 import (
    M1408_OUTPUT_MEDIA_TYPE,
    M1408_PROVISIONAL_ABI,
    DossierStatus,
    EvidenceDisposition,
    EvidenceLink,
    EvidenceLinkKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_SOURCE_ARTIFACT = {
    "artifact_id": "source-1",
    "version": "1.0.0",
    "digest": "sha256:" + "a" * 64,
    "media_type": "application/json",
}


def test_provisional_schemas_require_reconstructable_dossiers() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "evidence-link",
        "claim",
        "validation-route",
        "dossier",
        "configuration",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["reconstructableEvidenceChainRequired"] is True
        assert metadata["counterEvidenceRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1408_OUTPUT_MEDIA_TYPE
    assert M1408_PROVISIONAL_ABI is True
    assert DossierStatus.REVIEW_READY.value == "review_ready"


def test_supported_link_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        EvidenceLink(
            link_id="link-1",
            kind=EvidenceLinkKind.MECHANISM,
            source_artifact=_SOURCE_ARTIFACT,
            target_id="mechanism-1",
            claim="A mechanism link is supported.",
            disposition=EvidenceDisposition.SUPPORTED,
        )


def test_conflicted_link_is_not_silently_negative() -> None:
    link = EvidenceLink(
        link_id="link-2",
        kind=EvidenceLinkKind.COUNTER_EVIDENCE,
        source_artifact=_SOURCE_ARTIFACT,
        target_id="mechanism-1",
        claim="Counter-evidence remains unresolved.",
        disposition=EvidenceDisposition.CONFLICTED,
    )
    assert link.disposition is EvidenceDisposition.CONFLICTED
