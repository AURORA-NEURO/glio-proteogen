"""Focused contract/schema smoke for provisional M18-02."""

import pytest

from glio_proteogen.contracts.m18_02 import (
    M1802_OUTPUT_MEDIA_TYPE,
    M1802_PROVISIONAL_ABI,
    AlignmentDimension,
    AlignmentFindingCode,
    AlignmentObservationStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_all_alignment_dimensions() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["sampleTimeTerritoryAlignmentRequired"]
        and schema["x-glio-contract"]["analyteModalityReferenceAlignmentRequired"]
        and schema["x-glio-contract"]["biologicalContextAlignmentRequired"]
        and schema["x-glio-contract"]["conflictsPreserved"]
        and schema["x-glio-contract"]["discrepancyMapRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m18-01+json")
        and schema["x-glio-contract"]["parentTarget"] == "biomarker panel"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1802_OUTPUT_MEDIA_TYPE
    assert M1802_PROVISIONAL_ABI is True


def test_conflict_and_safe_alignment_states_are_explicit() -> None:
    assert AlignmentDimension.BIOLOGICAL_CONTEXT.value == "biological_context"
    assert AlignmentObservationStatus.CONFLICTED.value == "conflicted"
    assert AlignmentFindingCode.DISCREPANCY_UNRESOLVED.value == "discrepancy_unresolved"
    with pytest.raises(AssertionError):
        assert AlignmentObservationStatus.CONFLICTED is AlignmentObservationStatus.ALIGNED
