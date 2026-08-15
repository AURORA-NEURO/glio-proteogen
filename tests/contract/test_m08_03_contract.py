"""Focused contract/schema smoke for provisional M08-03."""

from glio_proteogen.contracts.m08_03 import (
    M0803_OUTPUT_MEDIA_TYPE,
    M0803_PROVISIONAL_ABI,
    BaselineMethod,
    contract_json_schemas,
)

_SCHEMA_COUNT = 6


def test_provisional_schemas_require_locked_baseline_evidence() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["benchmarkEvidenceRequired"] for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0803_OUTPUT_MEDIA_TYPE
    assert M0803_PROVISIONAL_ABI is True


def test_baseline_method_options_are_explicit_and_non_treatment() -> None:
    assert tuple(BaselineMethod) == (
        BaselineMethod.STATISTICAL_RULE_BASED,
        BaselineMethod.PATHWAY_ACTIVITY_NETWORK,
        BaselineMethod.SELECTIVE_ENSEMBLE_COMPLEX_GRAPH,
    )
