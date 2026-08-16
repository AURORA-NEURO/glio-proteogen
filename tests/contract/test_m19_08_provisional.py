"""Focused contract/schema smoke for provisional M19-08."""

from typing import cast

from glio_proteogen.contracts.m19_08 import (
    M1908_OUTPUT_MEDIA_TYPE,
    M1908_PROVISIONAL_ABI,
    RollbackDecision,
    TranslationFindingCode,
    TranslationHealthState,
    contract_json_schemas,
)

_SCHEMA_COUNT = 9


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


def test_provisional_schemas_require_translation_health_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(_metadata(schema)["provisionalAbi"] for schema in schemas.values())
    assert all(_metadata(schema)["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        _metadata(schema)["usageTelemetryRequired"]
        and _metadata(schema)["supportDriftRequired"]
        and _metadata(schema)["workflowEffectsRequired"]
        and _metadata(schema)["discrepanciesRequired"]
        and _metadata(schema)["suspensionRollbackRequired"]
        and _metadata(schema)["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        cast("str", _metadata(schema)["upstreamInputMediaType"]).endswith("m19-07+json")
        and _metadata(schema)["parentTarget"] == "proteotype"
        for schema in schemas.values()
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M1908_OUTPUT_MEDIA_TYPE
    assert M1908_PROVISIONAL_ABI is True


def test_health_and_rollback_states_are_explicit() -> None:
    assert TranslationHealthState.ROLLBACK_REQUIRED.value == "rollback_required"
    assert RollbackDecision.SUSPEND.value == "suspend"
    assert TranslationFindingCode.SUPPORT_DRIFT.value == "support_drift"
    assert str(RollbackDecision.SUSPEND.value) != str(RollbackDecision.NONE.value)
