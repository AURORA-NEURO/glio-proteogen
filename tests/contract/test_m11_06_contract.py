"""Focused contract/schema smoke for provisional M11-06."""

import pytest

from glio_proteogen.contracts.m11_06 import (
    M1106_OUTPUT_MEDIA_TYPE,
    M1106_PROVISIONAL_ABI,
    PerturbationKind,
    PerturbationResponseStatus,
    SensitivityResponse,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_bounded_sensitivity_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["boundedResponsesRequired"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["assumptionsRequired"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1106_OUTPUT_MEDIA_TYPE
    assert M1106_PROVISIONAL_ABI is True


def test_bounded_response_requires_ordered_envelope() -> None:
    response = SensitivityResponse(
        scenario_id="scenario.base",
        status=PerturbationResponseStatus.BOUNDED,
        response_value=0.5,
        lower_bound=0.2,
        upper_bound=0.8,
        assumptions=("Locked baseline assumption.",),
    )
    assert response.lower_bound <= response.response_value <= response.upper_bound
    assert PerturbationKind.MECHANISM_STRESS.value == "mechanism_stress"
    with pytest.raises(ValueError, match="bounded response"):
        SensitivityResponse(
            scenario_id="scenario.bad",
            status=PerturbationResponseStatus.BOUNDED,
            assumptions=("Missing response bounds.",),
        )
