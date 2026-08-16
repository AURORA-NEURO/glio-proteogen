"""Focused import/schema/safety smoke for provisional M06-06."""

import pytest

from glio_proteogen.contracts.m06_06 import (
    M0606_MAX_COMPONENTS,
    M0606_OUTPUT_MEDIA_TYPE,
    contract_json_schemas,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition import (
    M0606Plugin,
    M0606Service,
    M0606UncertaintyDecompositionAuthorizationError,
    preflight_uncertainty_decomposition_authorization,
)


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == M0606_MAX_COMPONENTS
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0606_OUTPUT_MEDIA_TYPE


def test_plugin_descriptor_and_preflight_fail_closed() -> None:
    descriptor = M0606Plugin(M0606Service()).descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M06-06"
    assert descriptor.version == "0.1.0-provisional"
    with pytest.raises(M0606UncertaintyDecompositionAuthorizationError):
        preflight_uncertainty_decomposition_authorization({"context": {"references": {}}})
