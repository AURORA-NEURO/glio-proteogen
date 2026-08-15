"""Focused contract/schema smoke for provisional M22-01."""

import pytest

from glio_proteogen.contracts.m22_01 import (
    M2201_OUTPUT_MEDIA_TYPE,
    M2201_PROVISIONAL_ABI,
    AdjudicationStatus,
    CurationStatus,
    ReferenceKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_locked_truth_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["referenceTruthRequired"]
        and schema["x-glio-contract"]["benchmarkPackageRequired"]
        and schema["x-glio-contract"]["controlsRequired"]
        and schema["x-glio-contract"]["adjudicationRequired"]
        and schema["x-glio-contract"]["endpointDefinitionRequired"]
        and schema["x-glio-contract"]["provenanceRequired"]
        and schema["x-glio-contract"]["inclusionAndChallengeSetRequired"]
        and schema["x-glio-contract"]["leakageAuditRequired"]
        and schema["x-glio-contract"]["lockProcedureRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "protein-RNA discordance"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2201_OUTPUT_MEDIA_TYPE
    assert M2201_PROVISIONAL_ABI is True


def test_reference_and_curation_states_are_explicit() -> None:
    assert ReferenceKind.CHALLENGE_SET.value == "challenge_set"
    assert AdjudicationStatus.LOCKED.value == "locked"
    assert CurationStatus.ABSTAINED.value == "abstained"
    with pytest.raises(AssertionError):
        assert CurationStatus.ABSTAINED is CurationStatus.CURATED
