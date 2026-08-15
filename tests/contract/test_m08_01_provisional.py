"""Focused schema and invariant smoke for provisional M08-01."""

from typing import Final

import pytest

from glio_proteogen.contracts.m08_01 import (
    M0801_OUTPUT_MEDIA_TYPE,
    FormalTranscriptProteinStateSchema,
    TranscriptProteinFeatureDefinition,
    TranscriptProteinFeatureValueKind,
    TranscriptProteinInvariant,
    TranscriptProteinInvariantSeverity,
    TranscriptProteinMissingness,
    contract_json_schemas,
)

_SCHEMA_COUNT: Final = 8


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0801_OUTPUT_MEDIA_TYPE


def test_formal_schema_rejects_invariants_outside_feature_domain() -> None:
    feature = TranscriptProteinFeatureDefinition(
        feature_id="discordance.scalar",
        version="0.1.0",
        value_kind=TranscriptProteinFeatureValueKind.SCALAR,
        unit="ratio",
        allowed_missingness=(TranscriptProteinMissingness.OBSERVED,),
    )
    invariant = TranscriptProteinInvariant(
        invariant_id="invariant.unknown",
        expression="unknown >= 0",
        severity=TranscriptProteinInvariantSeverity.ERROR,
        feature_ids=("unknown",),
    )
    with pytest.raises(ValueError, match="unknown feature"):
        FormalTranscriptProteinStateSchema(
            schema_id="schema.discordance",
            version="0.1.0",
            features=(feature,),
            invariants=(invariant,),
        )
