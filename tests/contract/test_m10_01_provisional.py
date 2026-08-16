"""Focused schema and invariant smoke for provisional M10-01."""

from typing import Final

import pytest

from glio_proteogen.contracts.m10_01 import (
    M1001_OUTPUT_MEDIA_TYPE,
    FormalProteinRnaDiscordanceStateSchema,
    ProteinRnaFeatureDefinition,
    ProteinRnaFeatureValueKind,
    ProteinRnaInvariant,
    ProteinRnaInvariantSeverity,
    ProteinRnaMissingness,
    contract_json_schemas,
)

_SCHEMA_COUNT: Final = 8


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1001_OUTPUT_MEDIA_TYPE


def test_formal_schema_rejects_invariants_outside_feature_domain() -> None:
    feature = ProteinRnaFeatureDefinition(
        feature_id="protein_rna.scalar",
        version="0.1.0",
        value_kind=ProteinRnaFeatureValueKind.SCALAR,
        unit="ratio",
        allowed_missingness=(ProteinRnaMissingness.OBSERVED,),
    )
    invariant = ProteinRnaInvariant(
        invariant_id="invariant.unknown",
        expression="unknown >= 0",
        severity=ProteinRnaInvariantSeverity.ERROR,
        feature_ids=("unknown",),
    )
    with pytest.raises(ValueError, match="unknown feature"):
        FormalProteinRnaDiscordanceStateSchema(
            schema_id="schema.protein_rna",
            version="0.1.0",
            features=(feature,),
            invariants=(invariant,),
        )
