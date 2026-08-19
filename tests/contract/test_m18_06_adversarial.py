"""Adversarial closure for the immutable M18-06 contract validators."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m18_06 import (
    AdjudicateBiomarkerPanelQueueRequest,
    AdjudicationRecord,
    AdjudicationRecordStatus,
    BiomarkerPanelAdjudicationResult,
    QueueResultStatus,
)
from glio_proteogen.contracts.m18_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.modules.c18_spatial_proteomics_projection.m18_06_reviewer_adjudication import (
    M1806AuthorizationError,
    M1806Engine,
    M1806ReplayError,
    preflight_m1806_authorization,
)
from tests.runtime.test_m18_06_adjudication import _request

_ZERO_DIGEST = "sha256:" + "0" * 64


def _record_payload() -> dict[str, object]:
    result = M1806Engine().adapt(_request())
    assert result.record is not None
    return result.record.model_dump(mode="python")


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("duplicate_entries", "discrepancy ids must be unique"),
        ("duplicate_assignments", "assignment ids must be unique"),
        ("duplicate_history", "audit event ids and sequence numbers must be unique"),
        ("unknown_assignment", "assignment references an unknown discrepancy"),
        ("resolved_without_summary", "resolved record requires a resolution summary"),
        ("escalated_with_summary", "escalated record cannot claim final resolution"),
    ],
)
def test_record_validator_rejects_each_incomplete_closure(field: str, message: str) -> None:
    payload = _record_payload()
    if field == "duplicate_entries":
        payload["entries"] = (payload["entries"][0], payload["entries"][0])
    elif field == "duplicate_assignments":
        payload["assignments"] = (payload["assignments"][0], payload["assignments"][0])
    elif field == "duplicate_history":
        payload["history"] = (payload["history"][0], payload["history"][0])
    elif field == "unknown_assignment":
        assignment = dict(payload["assignments"][0])
        assignment["discrepancy_id"] = "discrepancy.unknown"
        payload["assignments"] = (assignment,)
    elif field == "resolved_without_summary":
        payload["resolution_summary"] = None
    else:
        payload["status"] = AdjudicationRecordStatus.ESCALATED
        payload["resolution_summary"] = "illegitimate final resolution"

    with pytest.raises(ValueError, match=message):
        AdjudicationRecord.model_validate(payload, strict=True)


@pytest.mark.parametrize("mode", ["duplicate", "unknown"])
def test_request_validator_rejects_duplicate_or_unknown_assignment(mode: str) -> None:
    payload = _request().model_dump(mode="python")
    assignment = dict(payload["assignments"][0])
    if mode == "unknown":
        assignment["discrepancy_id"] = "discrepancy.unknown"
        payload["assignments"] = (assignment, payload["assignments"][1])
    else:
        payload["assignments"] = (assignment, assignment)

    with pytest.raises(
        ValueError,
        match=(
            r"request (assignment ids must be unique|assignment references an unknown discrepancy)"
        ),
    ):
        AdjudicateBiomarkerPanelQueueRequest.model_validate(payload, strict=True)


def test_result_validator_closes_request_record_abstention_and_digest() -> None:
    result = M1806Engine().adapt(_request())

    request_mismatch = result.model_dump(mode="python")
    request_mismatch["request_digest"] = _ZERO_DIGEST
    with pytest.raises(ValueError, match="request digest"):
        BiomarkerPanelAdjudicationResult.model_validate(request_mismatch, strict=True)

    missing_record = result.model_dump(mode="python")
    missing_record["record"] = None
    with pytest.raises(ValueError, match="recorded result requires"):
        BiomarkerPanelAdjudicationResult.model_validate(missing_record, strict=True)

    assert result.record is not None
    partial_record = result.record.model_dump(mode="python")
    partial_record["entries"] = (partial_record["entries"][0],)
    partial_record["assignments"] = (partial_record["assignments"][0],)
    partial_record["history"] = (partial_record["history"][0],)
    missing_entry = result.model_dump(mode="python")
    missing_entry["record"] = AdjudicationRecord.model_validate(partial_record, strict=True)
    with pytest.raises(ValueError, match="every requested discrepancy"):
        BiomarkerPanelAdjudicationResult.model_validate(missing_entry, strict=True)

    abstained_with_record = result.model_dump(mode="python")
    abstained_with_record["status"] = QueueResultStatus.ABSTAINED
    abstained_with_record["abstention_reason"] = "invalid record combination"
    with pytest.raises(ValueError, match="abstained result requires"):
        BiomarkerPanelAdjudicationResult.model_validate(abstained_with_record, strict=True)

    bad_digest = result.model_dump(mode="python")
    bad_digest["result_digest"] = _ZERO_DIGEST
    with pytest.raises(ValueError, match="result digest"):
        BiomarkerPanelAdjudicationResult.model_validate(bad_digest, strict=True)


def test_preflight_rejects_missing_controls_and_replay_rejects_request_tamper() -> None:
    with pytest.raises(M1806AuthorizationError, match="all seven"):
        preflight_m1806_authorization({"context": {}})

    result = M1806Engine().adapt(_request())
    tampered = result.model_copy(update={"request_digest": _ZERO_DIGEST})
    with pytest.raises(M1806ReplayError, match="request digest"):
        M1806Engine().replay(tampered)


def test_replay_rejects_semantic_tamper_with_recomputed_digest() -> None:
    result = M1806Engine().adapt(_request())
    tampered = result.model_copy(update={"human_review_required": False})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(M1806ReplayError, match="deterministic replay"):
        M1806Engine().replay(tampered)


def test_canonical_request_accepts_mapping_projection() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
