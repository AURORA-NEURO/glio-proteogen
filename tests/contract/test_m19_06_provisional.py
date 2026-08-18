"""Focused contract/schema and adversarial closure for provisional M19-06."""

from datetime import UTC, datetime
from typing import cast

import pytest

from glio_proteogen.contracts.m19_06 import (
    M1906_DOSSIER_SHA256,
    M1906_DOSSIER_SLICE,
    M1906_OUTPUT_MEDIA_TYPE,
    M1906_PROHIBITED_CLAIM_TERMS,
    M1906_PROVISIONAL_ABI,
    AdjudicateProteotypeQueueRequest,
    AdjudicationRecord,
    AdjudicationRecordStatus,
    AuditEventType,
    DiscrepancyQueueEntry,
    DiscrepancyReasonCode,
    DiscrepancySeverity,
    ImmutableAuditEvent,
    QueueEntryState,
    QueueResultStatus,
    ReviewDecision,
    ReviewerAssignment,
    ReviewWorkspaceConfiguration,
    audit_event_payload_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_SCHEMA_COUNT = 8
_TWO_REVIEWERS = 2


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


def test_provisional_schemas_require_immutable_review_history() -> None:
    schemas = contract_json_schemas()
    metadata = tuple(_metadata(schema) for schema in schemas.values())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(item["provisionalAbi"] for item in metadata)
    assert all(item["pendingOwnerConfirmation"] for item in metadata)
    assert all(
        item["structuredDisagreementRequired"]
        and item["reasonCodesRequired"]
        and item["blindedReviewSupported"]
        and item["escalationRequired"]
        and item["resolutionRequired"]
        and item["immutableHistoryRequired"]
        and item["contiguousAuditSequenceRequired"]
        and item["chainedAuditEventDigestRequired"]
        and item["criticalTwoReviewerMinimum"]
        and item["explicitAbstentionRequired"]
        and item["unsupportedToNegative"] is False
        for item in metadata
    )
    assert all(
        isinstance(item["upstreamInputMediaType"], str)
        and item["upstreamInputMediaType"].endswith("m19-05+json")
        and item["parentTarget"] == "proteotype"
        for item in metadata
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M1906_OUTPUT_MEDIA_TYPE
    assert M1906_PROVISIONAL_ABI is True
    assert str(_metadata(schemas["request"])["dossierSha256"]).endswith(
        M1906_DOSSIER_SHA256.removeprefix("sha256:")
    )
    assert _metadata(schemas["request"])["dossierSlice"] == M1906_DOSSIER_SLICE
    assert _metadata(schemas["request"])["prohibitedClaimTerms"] == list(
        M1906_PROHIBITED_CLAIM_TERMS
    )


def test_adjudication_states_and_safe_review_are_explicit() -> None:
    assert AdjudicationRecordStatus.ESCALATED.value == "escalated"
    assert DiscrepancySeverity.CRITICAL.value == "critical"
    assert QueueResultStatus.ABSTAINED.value == "abstained"
    assert ReviewDecision.ABSTAIN.value == "abstain"


_ZERO_DIGEST = "sha256:" + "0" * 64


def _artifact(artifact_id: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version="0.1.0-provisional",
        digest=_ZERO_DIGEST,
        media_type=media_type,
    )


def _context() -> ExecutionContext:
    artifact = _artifact("control.evidence")
    return ExecutionContext(
        request_id="request.1",
        actor_id="actor.1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="config.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="identity.1",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_ZERO_DIGEST,
                evidence=artifact,
            ),
            provenance=UpstreamDecisionReference(
                decision_id="provenance.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            consent=ConsentReference(
                decision_id="consent.1",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=UpstreamDecisionReference(
                decision_id="quality.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            support=UpstreamDecisionReference(
                decision_id="support.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="use.1",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
        ),
    )


def _evidence() -> tuple[EvidenceReference, ...]:
    artifact = _artifact("evidence.1")
    return (EvidenceReference(reference=artifact, role="evidence", claim="review evidence"),)


def _entry(
    *,
    discrepancy_id: str = "discrepancy.1",
    severity: DiscrepancySeverity = DiscrepancySeverity.ROUTINE,
    state: QueueEntryState = QueueEntryState.RESOLVED,
) -> DiscrepancyQueueEntry:
    return DiscrepancyQueueEntry(
        discrepancy_id=discrepancy_id,
        reason_code=DiscrepancyReasonCode.SOURCE_DISAGREEMENT,
        severity=severity,
        description="two evidence sources require structured review",
        state=state,
        evidence=_evidence(),
    )


def _assignment(
    *,
    discrepancy_id: str = "discrepancy.1",
    assignment_id: str = "assignment.1",
    reviewer_key: str = "reviewer.1",
    decision: ReviewDecision = ReviewDecision.ACCEPT,
) -> ReviewerAssignment:
    return ReviewerAssignment(
        assignment_id=assignment_id,
        discrepancy_id=discrepancy_id,
        reviewer_role="proteotype reviewer",
        reviewer_token=reviewer_key,
        decision=decision,
        rationale="reviewed source disagreement against the evidence bundle",
        evidence=_evidence(),
    )


def _event_payload(
    *,
    event_id: str = "event.1",
    event_type: AuditEventType = AuditEventType.RESOLVED,
    previous_event_digest: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "sequence": 1,
        "event_id": event_id,
        "event_type": event_type,
        "actor_token": "reviewer.1",
        "action": "recorded final adjudication",
        "record_digest": _ZERO_DIGEST,
        "previous_event_digest": previous_event_digest,
        "evidence": _evidence(),
    }
    payload["event_digest"] = audit_event_payload_digest(payload)
    return payload


def _record(
    *,
    entry: DiscrepancyQueueEntry | None = None,
    assignments: tuple[ReviewerAssignment, ...] | None = None,
    history: tuple[ImmutableAuditEvent, ...] | None = None,
    status: AdjudicationRecordStatus = AdjudicationRecordStatus.RESOLVED,
) -> AdjudicationRecord:
    actual_entry = entry or _entry()
    actual_assignments = assignments or (_assignment(discrepancy_id=actual_entry.discrepancy_id),)
    actual_history = history or (ImmutableAuditEvent.model_validate(_event_payload(), strict=True),)
    return AdjudicationRecord(
        record_id="record.1",
        version="0.1.0-provisional",
        entries=(actual_entry,),
        assignments=actual_assignments,
        history=actual_history,
        status=status,
        resolution_summary=(
            "resolved by blinded review" if status is AdjudicationRecordStatus.RESOLVED else None
        ),
        evidence=_evidence(),
    )


def _request(
    *,
    entries: tuple[DiscrepancyQueueEntry, ...] | None = None,
    assignments: tuple[ReviewerAssignment, ...] | None = None,
    source_artifacts: tuple[ArtifactReference, ...] | None = None,
) -> AdjudicateProteotypeQueueRequest:
    upstream = _artifact("upstream.1", "application/vnd.glio-proteogen.m19-05+json")
    actual_entries = entries or (_entry(),)
    return AdjudicateProteotypeQueueRequest(
        request_id="request.1",
        context=_context(),
        upstream_result=upstream,
        entries=actual_entries,
        assignments=assignments or (_assignment(discrepancy_id=actual_entries[0].discrepancy_id),),
        configuration=ReviewWorkspaceConfiguration(
            configuration_id="config.1",
            version="1.0.0",
            maximum_queue_entries=10,
        ),
        source_artifacts=source_artifacts or (upstream,),
    )


def test_audit_event_digest_is_stable_and_tamper_evident() -> None:
    payload = _event_payload()
    event = ImmutableAuditEvent.model_validate(payload, strict=True)
    assert audit_event_payload_digest(event) == event.event_digest
    tampered = dict(payload)
    tampered["action"] = "changed after signing"
    with pytest.raises(ValueError, match="audit event digest"):
        ImmutableAuditEvent.model_validate(tampered, strict=True)


def test_record_requires_contiguous_chained_history() -> None:
    first = _event_payload()
    second = _event_payload(
        event_id="event.2",
        event_type=AuditEventType.RESOLVED,
        previous_event_digest=str(first["event_digest"]),
    )
    second["sequence"] = 2
    second["event_digest"] = audit_event_payload_digest(second)
    valid = _record(
        history=(
            ImmutableAuditEvent.model_validate(first, strict=True),
            ImmutableAuditEvent.model_validate(second, strict=True),
        )
    )
    assert valid.history[-1].previous_event_digest == valid.history[0].event_digest
    broken = valid.model_dump(mode="python")
    broken_event = {**broken["history"][1], "previous_event_digest": _ZERO_DIGEST}
    broken_event["event_digest"] = audit_event_payload_digest(broken_event)
    broken["history"] = (broken["history"][0], broken_event)
    with pytest.raises(ValueError, match="previous digest"):
        AdjudicationRecord.model_validate(broken, strict=True)


def test_critical_discrepancy_requires_independent_blinded_reviewers() -> None:
    entry = _entry(severity=DiscrepancySeverity.CRITICAL)
    with pytest.raises(ValueError, match="two blinded reviewers"):
        _record(entry=entry)
    record = _record(
        entry=entry,
        assignments=(
            _assignment(discrepancy_id=entry.discrepancy_id),
            _assignment(
                discrepancy_id=entry.discrepancy_id,
                assignment_id="assignment.2",
                reviewer_key="reviewer.2",
                decision=ReviewDecision.REJECT,
            ),
        ),
    )
    assert len(record.assignments) == _TWO_REVIEWERS


def test_request_requires_upstream_artifact_in_source_manifest() -> None:
    with pytest.raises(ValueError, match="include the upstream result"):
        _request(source_artifacts=(_artifact("other.1"),))


def test_request_rejects_duplicate_blinded_reviewer_token() -> None:
    entry = _entry()
    with pytest.raises(ValueError, match="reviewed twice"):
        _request(
            assignments=(
                _assignment(discrepancy_id=entry.discrepancy_id),
                _assignment(
                    discrepancy_id=entry.discrepancy_id,
                    assignment_id="assignment.2",
                ),
            )
        )


@pytest.mark.parametrize(
    ("variant", "message"),
    [
        ("duplicate_entries", "discrepancy ids must be unique"),
        ("duplicate_assignments", "assignment ids must be unique"),
        ("duplicate_history", "audit event ids and sequence numbers must be unique"),
        ("noncontiguous_history", "audit history sequence must be contiguous"),
        ("unknown_assignment", "assignment references an unknown discrepancy"),
        ("duplicate_reviewer", "reviewed twice"),
        ("resolved_defer", "resolved discrepancy requires final review decisions"),
        ("missing_summary", "resolved record requires a resolution summary"),
        ("resolved_unresolved_entry", "every discrepancy to be resolved"),
        ("escalated_summary", "escalated record cannot claim final resolution"),
        ("escalated_without_unresolved", "escalated record requires an unresolved discrepancy"),
        ("wrong_terminal_event", "history must end with the record terminal state"),
    ],
)
def test_record_rejects_each_closed_history_variant(  # noqa: C901 - adversarial matrix.
    variant: str, message: str
) -> None:
    payload = _record().model_dump(mode="python")
    if variant == "duplicate_entries":
        payload["entries"] = (payload["entries"][0], payload["entries"][0])
    elif variant == "duplicate_assignments":
        payload["assignments"] = (payload["assignments"][0], payload["assignments"][0])
    elif variant == "duplicate_history":
        payload["history"] = (payload["history"][0], payload["history"][0])
    elif variant == "noncontiguous_history":
        event = dict(payload["history"][0])
        event["sequence"] = 2
        event["event_digest"] = audit_event_payload_digest(event)
        payload["history"] = (event,)
    elif variant == "unknown_assignment":
        assignment = dict(payload["assignments"][0])
        assignment["discrepancy_id"] = "discrepancy.unknown"
        payload["assignments"] = (assignment,)
    elif variant == "duplicate_reviewer":
        assignment = dict(payload["assignments"][0])
        assignment["assignment_id"] = "assignment.2"
        payload["assignments"] = (payload["assignments"][0], assignment)
    elif variant == "resolved_defer":
        assignment = dict(payload["assignments"][0])
        assignment["decision"] = ReviewDecision.DEFER
        payload["assignments"] = (assignment,)
    elif variant == "missing_summary":
        payload["resolution_summary"] = None
    elif variant == "resolved_unresolved_entry":
        entry = dict(payload["entries"][0])
        entry["state"] = QueueEntryState.IN_REVIEW
        payload["entries"] = (entry,)
    elif variant == "escalated_summary":
        payload["status"] = AdjudicationRecordStatus.ESCALATED
        payload["resolution_summary"] = "not allowed"
    elif variant == "escalated_without_unresolved":
        payload["status"] = AdjudicationRecordStatus.ESCALATED
        payload["resolution_summary"] = None
    else:
        event = dict(payload["history"][0])
        event["event_type"] = AuditEventType.QUEUE_CREATED
        event["event_digest"] = audit_event_payload_digest(event)
        payload["history"] = (event,)
    with pytest.raises(ValueError, match=message):
        AdjudicationRecord.model_validate(payload, strict=True)


def test_record_requires_assignment_for_every_entry() -> None:
    first = _entry()
    second = _entry(discrepancy_id="discrepancy.2")
    payload = _record().model_dump(mode="python")
    payload["entries"] = (first.model_dump(mode="python"), second.model_dump(mode="python"))
    with pytest.raises(ValueError, match="every discrepancy requires"):
        AdjudicationRecord.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("variant", "message"),
    [
        ("duplicate_assignment", "request assignment ids must be unique"),
        ("unknown_assignment", "request assignment references an unknown discrepancy"),
        ("duplicate_source", "request source artifact ids must be unique"),
        ("missing_source", "request source artifacts must include the upstream result"),
        ("missing_assignment", "every discrepancy requires a reviewer assignment"),
        ("critical_review", "critical discrepancy requires two blinded reviewers"),
    ],
)
def test_request_rejects_each_manifest_variant(variant: str, message: str) -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    if variant == "duplicate_assignment":
        payload["assignments"] = (payload["assignments"][0], payload["assignments"][0])
    elif variant == "unknown_assignment":
        assignment = dict(payload["assignments"][0])
        assignment["discrepancy_id"] = "discrepancy.unknown"
        payload["assignments"] = (assignment,)
    elif variant == "duplicate_source":
        payload["source_artifacts"] = (
            payload["source_artifacts"][0],
            payload["source_artifacts"][0],
        )
    elif variant == "missing_source":
        payload["source_artifacts"] = (_artifact("other.1"),)
    elif variant == "missing_assignment":
        second = _entry(discrepancy_id="discrepancy.2")
        payload["entries"] = (payload["entries"][0], second.model_dump(mode="python"))
    else:
        critical = _entry(severity=DiscrepancySeverity.CRITICAL)
        payload["entries"] = (critical.model_dump(mode="python"),)
        payload["assignments"] = (
            _assignment(discrepancy_id=critical.discrepancy_id).model_dump(mode="python"),
        )
    with pytest.raises(ValueError, match=message):
        AdjudicateProteotypeQueueRequest.model_validate(payload, strict=True)
