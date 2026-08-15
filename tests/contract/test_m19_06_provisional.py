"""Focused contract/schema smoke for provisional M19-06."""

import pytest

from glio_proteogen.contracts.m19_06 import (
    M1906_OUTPUT_MEDIA_TYPE,
    M1906_PROVISIONAL_ABI,
    AdjudicationRecordStatus,
    DiscrepancySeverity,
    QueueResultStatus,
    ReviewDecision,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_immutable_review_history() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["structuredDisagreementRequired"]
        and schema["x-glio-contract"]["reasonCodesRequired"]
        and schema["x-glio-contract"]["blindedReviewSupported"]
        and schema["x-glio-contract"]["escalationRequired"]
        and schema["x-glio-contract"]["resolutionRequired"]
        and schema["x-glio-contract"]["immutableHistoryRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m19-05+json")
        and schema["x-glio-contract"]["parentTarget"] == "proteotype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1906_OUTPUT_MEDIA_TYPE
    assert M1906_PROVISIONAL_ABI is True


def test_adjudication_states_and_safe_review_are_explicit() -> None:
    assert AdjudicationRecordStatus.ESCALATED.value == "escalated"
    assert DiscrepancySeverity.CRITICAL.value == "critical"
    assert QueueResultStatus.ABSTAINED.value == "abstained"
    assert ReviewDecision.ABSTAIN.value == "abstain"
    with pytest.raises(AssertionError):
        assert QueueResultStatus.ABSTAINED is QueueResultStatus.RECORDED
