"""Focused schema and rollback-control smoke for provisional M27-07."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m27_07 import (
    M2707_M2706_INPUT_MEDIA_TYPE,
    M2707_OUTPUT_MEDIA_TYPE,
    M2707_PROVISIONAL_ABI,
    ChangeKind,
    ChangeRisk,
    ComparisonStatus,
    PromotionState,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_CHANGE_KIND_COUNT = 6


def test_provisional_schemas_require_change_control_and_rollback() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "change",
        "revalidation",
        "comparison",
        "package",
        "rollback",
        "safe-failure",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["changeClassificationRequired"] is True
        assert metadata["impactAssessmentRequired"] is True
        assert metadata["revalidationRequired"] is True
        assert metadata["championChallengerRequired"] is True
        assert metadata["approvalRequired"] is True
        assert metadata["testedRollbackRequired"] is True
        assert metadata["criticalRegressionBlocksPromotion"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "complex activity"
        assert metadata["upstreamInputMediaType"] == M2707_M2706_INPUT_MEDIA_TYPE
    output_metadata = cast("dict[str, object]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2707_OUTPUT_MEDIA_TYPE
    assert M2707_PROVISIONAL_ABI is True


def test_change_states_and_risk_classes_are_explicit() -> None:
    assert len(tuple(ChangeKind)) == _CHANGE_KIND_COUNT
    assert ChangeRisk.CRITICAL.value == "critical"
    assert ComparisonStatus.FAILED.value == "failed"
    assert PromotionState.ROLLED_BACK.value == "rolled_back"
