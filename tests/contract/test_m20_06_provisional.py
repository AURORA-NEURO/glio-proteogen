"""Focused contract/schema smoke for provisional M20-06."""

import pytest

from glio_proteogen.contracts.m20_06 import (
    M2006_DOSSIER_SHA256,
    M2006_DOSSIER_SLICE,
    M2006_OUTPUT_MEDIA_TYPE,
    M2006_PROVISIONAL_ABI,
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
        schema["x-glio-contract"]["dossierSha256"] == M2006_DOSSIER_SHA256
        and schema["x-glio-contract"]["dossierSlice"] == M2006_DOSSIER_SLICE
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m20-05+json")
        and schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2006_OUTPUT_MEDIA_TYPE
    assert M2006_PROVISIONAL_ABI is True


def test_adjudication_states_and_safe_review_are_explicit() -> None:
    assert AdjudicationRecordStatus.ESCALATED.value == "escalated"
    assert DiscrepancySeverity.CRITICAL.value == "critical"
    assert QueueResultStatus.ABSTAINED.value == "abstained"
    assert ReviewDecision.ABSTAIN.value == "abstain"
    with pytest.raises(AssertionError):
        assert QueueResultStatus.ABSTAINED is QueueResultStatus.RECORDED
