"""Focused import/schema/safety smoke for provisional M08-07."""

from typing import Final

import pytest

from glio_proteogen.contracts.m08_07 import (
    M0807_OUTPUT_MEDIA_TYPE,
    PredictionSet,
    contract_json_schemas,
)
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_07_calibration_selective_prediction as runtime,
)

_SCHEMA_COUNT: Final = 8
_PREDICTION_SET_SIZE: Final = 2


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0807_OUTPUT_MEDIA_TYPE


def test_prediction_set_and_preflight_fail_closed() -> None:
    prediction_set = PredictionSet(labels=("subtype_a", "subtype_b"), nominal_coverage=0.9)
    assert len(prediction_set.labels) == _PREDICTION_SET_SIZE
    with pytest.raises(runtime.M0807AuthorizationError):
        runtime.preflight_m0807_authorization({"context": {"references": {}}})
    assert runtime.M0807Plugin(runtime.M0807Service()).descriptor().module_id == (
        "GLIO-PROTEOGEN-M08-07"
    )
