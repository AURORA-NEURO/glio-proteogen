"""Focused contract/schema smoke for provisional M21-07."""

import pytest

from glio_proteogen.contracts.m21_07 import (
    M2107_OUTPUT_MEDIA_TYPE,
    M2107_PROVISIONAL_ABI,
    EvaluationStatus,
    OperationalDimension,
    OperationalStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_operational_safety_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["reviewerComprehensionRequired"]
        and schema["x-glio-contract"]["automationBiasAssessmentRequired"]
        and schema["x-glio-contract"]["throughputLatencyRequired"]
        and schema["x-glio-contract"]["downtimeRecoveryRequired"]
        and schema["x-glio-contract"]["fallbackRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m21-06+json")
        and schema["x-glio-contract"]["parentTarget"] == "complex activity"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2107_OUTPUT_MEDIA_TYPE
    assert M2107_PROVISIONAL_ABI is True


def test_operational_dimensions_and_safe_states_are_explicit() -> None:
    assert OperationalDimension.AUTOMATION_BIAS.value == "automation_bias"
    assert OperationalDimension.FALLBACK.value == "fallback"
    assert OperationalStatus.NOT_EVALUABLE.value == "not_evaluable"
    assert EvaluationStatus.ABSTAINED.value == "abstained"
    with pytest.raises(AssertionError):
        assert EvaluationStatus.ABSTAINED is EvaluationStatus.EVALUATED
