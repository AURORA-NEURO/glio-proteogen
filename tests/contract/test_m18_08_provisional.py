"""Focused contract/schema smoke for provisional M18-08."""

import pytest

from glio_proteogen.contracts.m18_08 import (
    M1808_OUTPUT_MEDIA_TYPE,
    M1808_PROVISIONAL_ABI,
    RollbackDecision,
    TranslationFindingCode,
    TranslationHealthState,
    contract_json_schemas,
)

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_translation_health_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["usageTelemetryRequired"]
        and schema["x-glio-contract"]["supportDriftRequired"]
        and schema["x-glio-contract"]["workflowEffectsRequired"]
        and schema["x-glio-contract"]["discrepanciesRequired"]
        and schema["x-glio-contract"]["suspensionRollbackRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m18-07+json")
        and schema["x-glio-contract"]["parentTarget"] == "biomarker panel"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1808_OUTPUT_MEDIA_TYPE
    assert M1808_PROVISIONAL_ABI is True


def test_health_and_rollback_states_are_explicit() -> None:
    assert TranslationHealthState.ROLLBACK_REQUIRED.value == "rollback_required"
    assert RollbackDecision.SUSPEND.value == "suspend"
    assert TranslationFindingCode.SUPPORT_DRIFT.value == "support_drift"
    with pytest.raises(AssertionError):
        assert RollbackDecision.SUSPEND is RollbackDecision.NONE
