"""Focused contract/schema smoke for provisional M17-04."""

import pytest

from glio_proteogen.contracts.m17_04 import (
    M1704_OUTPUT_MEDIA_TYPE,
    M1704_PROVISIONAL_ABI,
    AdapterFindingCode,
    IntendedUseKind,
    PolicyDecisionStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_bounded_use_policy() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["intendedUseRegistrationRequired"]
        and schema["x-glio-contract"]["evidenceTierRequired"]
        and schema["x-glio-contract"]["claimCeilingRequired"]
        and schema["x-glio-contract"]["displaySemanticsRequired"]
        and schema["x-glio-contract"]["policyDecisionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m17-03+json")
        and schema["x-glio-contract"]["parentTarget"] == "variant peptide"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1704_OUTPUT_MEDIA_TYPE
    assert M1704_PROVISIONAL_ABI is True


def test_policy_and_treatment_block_are_explicit() -> None:
    assert IntendedUseKind.CLINICAL_REVIEW.value == "clinical_review"
    assert PolicyDecisionStatus.BLOCKED.value == "blocked"
    assert AdapterFindingCode.TREATMENT_RECOMMENDATION_BLOCKED.value == (
        "treatment_recommendation_blocked"
    )
    with pytest.raises(AssertionError):
        assert PolicyDecisionStatus.BLOCKED is PolicyDecisionStatus.ALLOWED
