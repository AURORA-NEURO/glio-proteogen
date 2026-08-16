"""Focused schema and conflict-preservation smoke for provisional M19-02."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m19_02 import (
    M1902_M1901_INPUT_MEDIA_TYPE,
    M1902_OUTPUT_MEDIA_TYPE,
    M1902_PROVISIONAL_ABI,
    AlignmentDimension,
    AlignmentStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7
_ALIGNMENT_DIMENSION_COUNT = 7


def test_provisional_schemas_require_alignment_and_conflict_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "aligned-bundle",
        "configuration",
        "observation",
        "discrepancy",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["sampleTimeTerritoryAlignmentRequired"] is True
        assert metadata["analyteModalityReferenceAlignmentRequired"] is True
        assert metadata["biologicalContextAlignmentRequired"] is True
        assert metadata["conflictsPreserved"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "proteotype"
        assert metadata["upstreamInputMediaType"] == M1902_M1901_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1902_OUTPUT_MEDIA_TYPE
    assert M1902_PROVISIONAL_ABI is True


def test_all_alignment_dimensions_and_safe_abstention_are_explicit() -> None:
    assert len(tuple(AlignmentDimension)) == _ALIGNMENT_DIMENSION_COUNT
    assert AlignmentDimension.BIOLOGICAL_CONTEXT.value == "biological_context"
    assert AlignmentStatus.ALIGNED.value == "aligned"
    assert AlignmentStatus.ABSTAINED.value == "abstained"
