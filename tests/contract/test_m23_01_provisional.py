"""Focused contract/schema smoke for provisional M23-01."""

from typing import Any, cast

import pytest

from glio_proteogen.contracts.m23_01 import (
    M2301_OUTPUT_MEDIA_TYPE,
    M2301_PROVISIONAL_ABI,
    AdjudicationStatus,
    CurationStatus,
    ReferenceKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_locked_truth_controls() -> None:
    schemas = contract_json_schemas()
    typed_schemas = cast("dict[str, dict[str, Any]]", schemas)
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in typed_schemas.values())
    assert all(
        schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in typed_schemas.values()
    )
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
        for schema in typed_schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "variant peptide"
        for schema in typed_schemas.values()
    )
    assert typed_schemas["output"]["x-glio-contract"]["outputMediaType"] == M2301_OUTPUT_MEDIA_TYPE
    assert M2301_PROVISIONAL_ABI is True


def test_reference_and_curation_states_are_explicit() -> None:
    assert ReferenceKind.CHALLENGE_SET.value == "challenge_set"
    assert AdjudicationStatus.LOCKED.value == "locked"
    assert CurationStatus.ABSTAINED.value == "abstained"
    with pytest.raises(AssertionError):
        assert cast("object", CurationStatus.ABSTAINED) is cast("object", CurationStatus.CURATED)
