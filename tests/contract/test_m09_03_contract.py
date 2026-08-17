"""Focused contract/schema smoke for provisional M09-03."""

from glio_proteogen.contracts import m09_03 as m0903
from glio_proteogen.contracts.m09_03 import (
    M0903_OUTPUT_MEDIA_TYPE,
    M0903_PROVISIONAL_ABI,
    BaselineMethod,
    contract_json_schemas,
)

_SCHEMA_COUNT = 5


def test_public_exports_are_defined_by_the_contract_package() -> None:
    assert all(hasattr(m0903, name) for name in m0903.__all__)


def test_provisional_schemas_require_locked_baseline_evidence() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["benchmarkEvidenceRequired"] for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0903_OUTPUT_MEDIA_TYPE
    assert M0903_PROVISIONAL_ABI is True


def test_baseline_method_options_are_explicit_and_non_treatment() -> None:
    assert tuple(BaselineMethod) == (
        BaselineMethod.STATISTICAL_RULE_BASED,
        BaselineMethod.STOICHIOMETRIC_FACTORIZATION,
        BaselineMethod.SELECTIVE_ENSEMBLE_PATHWAY_NETWORK,
    )
