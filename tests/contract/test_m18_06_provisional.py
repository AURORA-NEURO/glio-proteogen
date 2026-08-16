"""Focused schema and immutable-review smoke for provisional M18-06."""

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m18_06 import (
    M1806_DOSSIER_SHA256,
    M1806_DOSSIER_SLICE,
    M1806_M1805_INPUT_MEDIA_TYPE,
    M1806_OUTPUT_MEDIA_TYPE,
    M1806_PROVISIONAL_ABI,
    DiscrepancyReasonCode,
    QueueEntryState,
    QueueFindingCode,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_review_queue_invariants() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "record",
        "queue-entry",
        "assignment",
        "audit-event",
        "configuration",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["structuredDisagreementRequired"] is True
        assert metadata["reasonCodesRequired"] is True
        assert metadata["blindedReviewSupported"] is True
        assert metadata["immutableHistoryRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "biomarker panel"
        assert metadata["upstreamInputMediaType"] == M1806_M1805_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1806_OUTPUT_MEDIA_TYPE
    assert M1806_PROVISIONAL_ABI is True
    assert schemas["request"]["x-glio-contract"]["dossierSha256"].endswith(
        M1806_DOSSIER_SHA256.removeprefix("sha256:")
    )
    assert schemas["request"]["x-glio-contract"]["dossierSlice"].endswith(
        M1806_DOSSIER_SLICE
    )


def test_queue_reason_and_safe_state_are_explicit() -> None:
    assert DiscrepancyReasonCode.IDENTITY_CONFLICT.value == "identity_conflict"
    assert QueueEntryState.ESCALATED.value == "escalated"
    assert QueueFindingCode.CRITICAL_UNRESOLVED.value == "critical_unresolved"
    with pytest.raises(AssertionError):
        assert QueueEntryState.ESCALATED is QueueEntryState.RESOLVED
