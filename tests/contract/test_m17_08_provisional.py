"""Focused contract/schema smoke for provisional M17-08."""

import pytest

from glio_proteogen.contracts.m17_08 import (
    M1708_DOSSIER_SHA256,
    M1708_DOSSIER_SLICE,
    M1708_OUTPUT_MEDIA_TYPE,
    M1708_PROVISIONAL_ABI,
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
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m17-07+json")
        and schema["x-glio-contract"]["parentTarget"] == "variant peptide"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1708_OUTPUT_MEDIA_TYPE
    assert M1708_PROVISIONAL_ABI is True
    assert schemas["request"]["x-glio-contract"]["dossierSha256"].endswith(
        M1708_DOSSIER_SHA256.removeprefix("sha256:")
    )
    assert schemas["request"]["x-glio-contract"]["dossierSlice"].endswith(
        M1708_DOSSIER_SLICE
    )


def test_health_and_rollback_states_are_explicit() -> None:
    assert TranslationHealthState.ROLLBACK_REQUIRED.value == "rollback_required"
    assert RollbackDecision.SUSPEND.value == "suspend"
    assert TranslationFindingCode.SUPPORT_DRIFT.value == "support_drift"
    with pytest.raises(AssertionError):
        assert RollbackDecision.SUSPEND is RollbackDecision.NONE
