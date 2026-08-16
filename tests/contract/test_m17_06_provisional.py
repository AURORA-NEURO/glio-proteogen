"""Focused contract/schema smoke for provisional M17-06."""

import pytest

from glio_proteogen.contracts.m17_06 import (
    M1706_OUTPUT_MEDIA_TYPE,
    M1706_PROVISIONAL_ABI,
    DiscrepancyReasonCode,
    QueueEntryState,
    QueueFindingCode,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_review_queue_invariants() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["structuredDisagreementRequired"]
        and schema["x-glio-contract"]["reasonCodesRequired"]
        and schema["x-glio-contract"]["blindedReviewSupported"]
        and schema["x-glio-contract"]["immutableHistoryRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m17-05+json")
        and schema["x-glio-contract"]["parentTarget"] == "variant peptide"
        and schema["x-glio-contract"]["primaryArchitecture"] == "contrastive_protein_encoder"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1706_OUTPUT_MEDIA_TYPE
    assert M1706_PROVISIONAL_ABI is True


def test_queue_reason_and_safe_state_are_explicit() -> None:
    assert DiscrepancyReasonCode.IDENTITY_CONFLICT.value == "identity_conflict"
    assert QueueEntryState.ESCALATED.value == "escalated"
    assert QueueFindingCode.CRITICAL_UNRESOLVED.value == "critical_unresolved"
    with pytest.raises(AssertionError):
        assert QueueEntryState.ESCALATED is QueueEntryState.RESOLVED
