"""Focused contract/schema smoke for provisional M15-02."""

import pytest

from glio_proteogen.contracts.m15_02 import (
    M1502_DOSSIER_SHA256,
    M1502_DOSSIER_SLICE,
    M1502_OUTPUT_MEDIA_TYPE,
    M1502_PROVISIONAL_ABI,
    ContextDimension,
    ContextEvaluationStatus,
    ContextFindingCode,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_preserve_context_and_safe_failure() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["contextDimensionsExplicit"]
        and schema["x-glio-contract"]["applicableMechanismsExplicit"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["primaryArchitecture"] == "elastic_net_consequence_model"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1502_OUTPUT_MEDIA_TYPE
    assert M1502_PROVISIONAL_ABI is True
    assert M1502_DOSSIER_SHA256 == (
        "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M1502_DOSSIER_SLICE.endswith(":5120-5160")
    assert all(schema["x-glio-contract"]["dossierSlice"] == M1502_DOSSIER_SLICE for schema in schemas.values())


def test_context_dimensions_and_abstention_are_explicit() -> None:
    assert ContextDimension.TERRITORY.value == "territory"
    assert ContextEvaluationStatus.NOT_EVALUABLE.value == "not_evaluable"
    assert ContextFindingCode.UNSUPPORTED_CONTEXT.value == "unsupported_context"
    with pytest.raises(AssertionError):
        assert ContextEvaluationStatus.NOT_EVALUABLE is ContextEvaluationStatus.SUPPORTED
