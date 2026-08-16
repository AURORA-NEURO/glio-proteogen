"""Focused contract/schema smoke for provisional M16-03."""

import pytest

from glio_proteogen.contracts.m16_03 import (
    M1603_OUTPUT_MEDIA_TYPE,
    M1603_PROVISIONAL_ABI,
    DisagreementStatus,
    FusionFindingCode,
    SourceKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_preserve_attribution_and_conflicts() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["componentSpecificIntegration"]
        and schema["x-glio-contract"]["sourceAttributionRequired"]
        and schema["x-glio-contract"]["disagreementPreserved"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m16-02+json")
        and schema["x-glio-contract"]["parentTarget"] == "protein-RNA discordance"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1603_OUTPUT_MEDIA_TYPE
    assert M1603_PROVISIONAL_ABI is True


def test_source_kinds_and_open_disagreement_are_explicit() -> None:
    assert SourceKind.TRANSCRIPTOME.value == "transcriptome"
    assert DisagreementStatus.OPEN.value == "open"
    assert FusionFindingCode.SOURCE_DISAGREEMENT.value == "source_disagreement"
    with pytest.raises(AssertionError):
        assert DisagreementStatus.OPEN is DisagreementStatus.RESOLVED
