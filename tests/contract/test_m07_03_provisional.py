"""Focused import/schema/safety smoke for provisional M07-03."""

from typing import Final

import pytest

from glio_proteogen.contracts.m07_03 import (
    M0703_OUTPUT_MEDIA_TYPE,
    contract_json_schemas,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_03_mature_baseline_estimator import (
    M0703AuthorizationError,
    M0703Plugin,
    M0703Service,
    preflight_m0703_authorization,
)

_SCHEMA_COUNT: Final = 7


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0703_OUTPUT_MEDIA_TYPE


def test_plugin_descriptor_and_preflight_fail_closed() -> None:
    descriptor = M0703Plugin(M0703Service()).descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M07-03"
    assert descriptor.version == "0.1.0-provisional"
    with pytest.raises(M0703AuthorizationError):
        preflight_m0703_authorization({"context": {"references": {}}})
