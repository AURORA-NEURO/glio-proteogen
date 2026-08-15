"""Focused contract/schema smoke for provisional M19-03."""

import pytest

from glio_proteogen.contracts.m19_03 import (
    M1903_OUTPUT_MEDIA_TYPE,
    M1903_PROVISIONAL_ABI,
    DisagreementStatus,
    FusionStatus,
    ReliabilityBand,
    SourceKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_preserve_attribution_and_conflict() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["sourceAttributionRequired"]
        and schema["x-glio-contract"]["reliabilityRequired"]
        and schema["x-glio-contract"]["uncertaintyRequired"]
        and schema["x-glio-contract"]["disagreementPreservationRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m19-02+json")
        and schema["x-glio-contract"]["parentTarget"] == "proteotype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1903_OUTPUT_MEDIA_TYPE
    assert M1903_PROVISIONAL_ABI is True


def test_fusion_states_and_source_ownership_are_explicit() -> None:
    assert SourceKind.IMMUNOPEPTIDOMIC_EVIDENCE.value == "immunopeptidomic_evidence"
    assert ReliabilityBand.NOT_EVALUABLE.value == "not_evaluable"
    assert DisagreementStatus.OPEN.value == "open"
    assert FusionStatus.ABSTAINED.value == "abstained"
    with pytest.raises(AssertionError):
        assert FusionStatus.ABSTAINED is FusionStatus.INTEGRATED
