"""Focused schema and source-attribution smoke for provisional M18-03."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m18_03 import (
    M1803_M1802_INPUT_MEDIA_TYPE,
    M1803_OUTPUT_MEDIA_TYPE,
    M1803_PROVISIONAL_ABI,
    FusionStatus,
    ReliabilityBand,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_attribution_and_conflict_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "integrated-evidence",
        "source-contribution",
        "disagreement",
        "aggregation",
        "configuration",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["sourceAttributionRequired"] is True
        assert metadata["reliabilityRequired"] is True
        assert metadata["disagreementPreserved"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1803_OUTPUT_MEDIA_TYPE
    assert schemas["request"]["x-glio-contract"]["upstreamInputMediaType"] == (
        M1803_M1802_INPUT_MEDIA_TYPE
    )
    assert M1803_PROVISIONAL_ABI is True


def test_fusion_states_keep_reliability_and_safe_abstention_explicit() -> None:
    assert FusionStatus.INTEGRATED.value == "integrated"
    assert FusionStatus.ABSTAINED.value == "abstained"
    assert ReliabilityBand.NOT_EVALUABLE.value == "not_evaluable"
