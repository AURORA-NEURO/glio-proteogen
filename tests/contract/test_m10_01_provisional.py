"""Focused schema and invariant smoke for provisional M10-01."""

from typing import Final

import pytest

from glio_proteogen.contracts.m10_01 import (
    M1001_OUTPUT_MEDIA_TYPE,
    FormalProteinRnaDiscordanceStateSchema,
    ProteinRnaFeatureDefinition,
    ProteinRnaFeatureValue,
    ProteinRnaFeatureValueKind,
    ProteinRnaInvariant,
    ProteinRnaInvariantSeverity,
    ProteinRnaMissingness,
    ProteinRnaMigrationRule,
    contract_json_schemas,
)

_SCHEMA_COUNT: Final = 9


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


def test_invariants_are_declarative_and_bounded() -> None:
    with pytest.raises(ValueError, match="declarative"):
        ProteinRnaInvariant(
            invariant_id="invariant.eval",
            expression="__import__('os').system('echo unsafe')",
            severity=ProteinRnaInvariantSeverity.ERROR,
            feature_ids=("protein_rna.scalar",),
        )


def test_feature_values_reject_non_finite_and_migrations_reject_duplicates() -> None:
    with pytest.raises(ValueError, match="finite"):
        ProteinRnaFeatureValue(
            feature_id="protein_rna.scalar",
            state=ProteinRnaMissingness.OBSERVED,
            unit="ratio",
            scalar_value=float("inf"),
        )
    with pytest.raises(ValueError, match="unique"):
        ProteinRnaMigrationRule(
            source_version="0.1.0",
            target_version="0.2.0",
            mapped_feature_ids=("protein_rna.scalar", "protein_rna.scalar"),
            lossy=False,
        )
