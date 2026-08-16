"""Focused contract/schema smoke for provisional M25-03."""

from typing import Any, cast

from glio_proteogen.contracts.m25_03 import (
    M2503_OUTPUT_MEDIA_TYPE,
    M2503_PROVISIONAL_ABI,
    BaselineKind,
    BenchmarkStatus,
    ValidationStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_locked_benchmark_controls() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["nestedValidationRequired"]
        and schema["x-glio-contract"]["lockedSplitsRequired"]
        and schema["x-glio-contract"]["simpleBaselineRequired"]
        and schema["x-glio-contract"]["matureBaselineRequired"]
        and schema["x-glio-contract"]["componentAblationRequired"]
        and schema["x-glio-contract"]["computeMatchedComparisonRequired"]
        and schema["x-glio-contract"]["uncertaintyStabilityAbstention"]
        and schema["x-glio-contract"]["proteinInteractionGnnRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m25-02+json")
        and schema["x-glio-contract"]["parentTarget"] == "proteotype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2503_OUTPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["primaryArchitecture"] == "protein_interaction_gnn"
    assert schemas["output"]["x-glio-contract"]["fallbackArchitecture"] == "protein_complex_graph"
    assert M2503_PROVISIONAL_ABI is True


def test_benchmark_states_and_baseline_kinds_are_explicit() -> None:
    assert BaselineKind.SIMPLE.value == "simple"
    assert BaselineKind.MATURE.value == "mature"
    assert BenchmarkStatus.ABSTAINED.value == "abstained"
    assert ValidationStatus.NOT_EVALUABLE.value == "not_evaluable"
    assert tuple(BenchmarkStatus) == (BenchmarkStatus.COMPLETED, BenchmarkStatus.ABSTAINED)
