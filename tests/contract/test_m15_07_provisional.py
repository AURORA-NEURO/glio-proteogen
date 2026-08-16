"""Focused contract/schema smoke for provisional M15-07."""

import pytest

from glio_proteogen.contracts.m15_07 import (
    M1507_OUTPUT_MEDIA_TYPE,
    M1507_PROVISIONAL_ABI,
    ControlOutcome,
    PlausibilityFindingCode,
    contract_json_schemas,
)

_SCHEMA_COUNT = 6


def test_provisional_schemas_require_controls_and_conflict_preservation() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["failedControlsBlockRelease"]
        and schema["x-glio-contract"]["conflictsPreserved"]
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["primaryArchitecture"] == "longitudinal_state_space"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1507_OUTPUT_MEDIA_TYPE
    assert M1507_PROVISIONAL_ABI is True


def test_control_outcomes_include_non_evaluable_safe_path() -> None:
    assert ControlOutcome.NOT_EVALUABLE.value == "not_evaluable"
    assert PlausibilityFindingCode.UNRESOLVED_CONFLICT.value == "unresolved_conflict"
    with pytest.raises(AssertionError):
        assert ControlOutcome.NOT_EVALUABLE is ControlOutcome.PASSED
