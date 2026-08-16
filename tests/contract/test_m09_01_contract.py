"""Focused schema and invariant smoke for provisional M09-01."""

from typing import Final

import pytest

from glio_proteogen.contracts.m09_01 import (
    M0901_OUTPUT_MEDIA_TYPE,
    ComplexActivityFeatureDefinition,
    ComplexActivityFeatureValueKind,
    ComplexActivityInvariant,
    ComplexActivityInvariantSeverity,
    ComplexActivityMissingness,
    FormalComplexActivityStateSchema,
    contract_json_schemas,
)

_SCHEMA_COUNT: Final = 10


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["executableInvariantLibrary"]
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0901_OUTPUT_MEDIA_TYPE


def test_formal_schema_rejects_invariants_outside_feature_domain() -> None:
    feature = ComplexActivityFeatureDefinition(
        feature_id="complex.activity.scalar",
        version="0.1.0",
        value_kind=ComplexActivityFeatureValueKind.SCALAR,
        unit="activity",
        allowed_missingness=(ComplexActivityMissingness.OBSERVED,),
    )
    invariant = ComplexActivityInvariant(
        invariant_id="invariant.unknown",
        expression="unknown >= 0",
        severity=ComplexActivityInvariantSeverity.ERROR,
        feature_ids=("unknown",),
    )
    with pytest.raises(ValueError, match="unknown feature"):
        FormalComplexActivityStateSchema(
            schema_id="schema.complex-activity",
            version="0.1.0",
            features=(feature,),
            invariants=(invariant,),
        )
