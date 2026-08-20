"""Adversarial contract and replay coverage for provisional M20-06."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m20_06 import (
    M2006_M2005_INPUT_MEDIA_TYPE,
    AdjudicateProteinSubtypeQueueRequest,
    AdjudicationRecord,
    AdjudicationRecordStatus,
    DiscrepancyQueueEntry,
    DiscrepancyReasonCode,
    DiscrepancySeverity,
    ImmutableAuditEvent,
    QueueEntryState,
    ReviewDecision,
    ReviewerAssignment,
    ReviewWorkspaceConfiguration,
    canonical_request_bytes,
    canonical_request_digest,
    canonical_result_payload_bytes,
    result_payload_digest,
    verify_request_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2006.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2006:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M20-06 adjudication evidence.",
    )


def _reviewer_token() -> str:
    return "reviewer." + "m2006.one"


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2006.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context(request_id: str) -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended_use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2006.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2006.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2006.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2006.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _entry(
    name: str = "one", state: QueueEntryState = QueueEntryState.RESOLVED
) -> DiscrepancyQueueEntry:
    evidence = _artifact(f"entry-{name}")
    return DiscrepancyQueueEntry(
        discrepancy_id=f"discrepancy.m2006.{name}",
        reason_code=DiscrepancyReasonCode.SOURCE_DISAGREEMENT,
        severity=DiscrepancySeverity.MATERIAL,
        description="A synthetic discrepancy remains attributable to its source.",
        state=state,
        evidence=(_evidence(evidence),),
    )


def _assignment(
    entry: DiscrepancyQueueEntry,
    *,
    reviewer_token: str | None = None,
    decision: ReviewDecision = ReviewDecision.ACCEPT,
) -> ReviewerAssignment:
    evidence = _artifact(f"assignment-{entry.discrepancy_id}")
    return ReviewerAssignment(
        assignment_id=f"assignment.m2006.{entry.discrepancy_id.rsplit('.', 1)[-1]}",
        discrepancy_id=entry.discrepancy_id,
        reviewer_role="independent adjudicator",
        reviewer_token=reviewer_token or _reviewer_token(),
        decision=decision,
        rationale="The reviewer decision is explicitly recorded for audit.",
        evidence=(_evidence(evidence),),
    )


def _record(
    entry: DiscrepancyQueueEntry,
    assignment: ReviewerAssignment,
    *,
    status: AdjudicationRecordStatus = AdjudicationRecordStatus.RESOLVED,
) -> AdjudicationRecord:
    record_evidence = _artifact("record")
    return AdjudicationRecord(
        record_id="record.m2006.synthetic",
        version="1.0.0",
        entries=(entry,),
        assignments=(assignment,),
        history=(
            ImmutableAuditEvent(
                sequence=1,
                event_id="event.m2006.one",
                event_type="adjudication_recorded",
                actor_token=_reviewer_token(),
                action="recorded",
                record_digest=sha256_digest("record.m2006.synthetic"),
                evidence=(_evidence(record_evidence),),
            ),
        ),
        status=status,
        resolution_summary=(
            "Resolution recorded from explicit review."
            if status is AdjudicationRecordStatus.RESOLVED
            else None
        ),
        evidence=(_evidence(record_evidence),),
    )


def _request() -> AdjudicateProteinSubtypeQueueRequest:
    upstream = _artifact("upstream", M2006_M2005_INPUT_MEDIA_TYPE)
    entry = _entry()
    assignment = _assignment(entry)
    configuration_evidence = _artifact("configuration")
    return AdjudicateProteinSubtypeQueueRequest(
        request_id="request.m2006.synthetic",
        context=_context("request.m2006.synthetic"),
        upstream_result=upstream,
        entries=(entry,),
        assignments=(assignment,),
        configuration=ReviewWorkspaceConfiguration(
            configuration_id="configuration.m2006.synthetic",
            version="1.0.0",
            maximum_queue_entries=16,
            evidence=(_evidence(configuration_evidence),),
        ),
        source_artifacts=(upstream,),
    )


def test_resolved_record_requires_final_entries_and_decisions() -> None:
    entry = _entry()
    assignment = _assignment(entry)
    assert _record(entry, assignment).status is AdjudicationRecordStatus.RESOLVED
    with pytest.raises(ValueError, match="every entry to be resolved"):
        AdjudicationRecord.model_validate(
            _record(entry, assignment).model_copy(
                update={"entries": (_entry(state=QueueEntryState.IN_REVIEW),)}
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="deferred or abstained"):
        AdjudicationRecord.model_validate(
            _record(entry, _assignment(entry, decision=ReviewDecision.DEFER)),
            strict=True,
        )


def test_escalated_record_requires_an_escalated_entry() -> None:
    entry = _entry()
    assignment = _assignment(entry, decision=ReviewDecision.DEFER)
    with pytest.raises(ValueError, match="escalated or non-evaluable"):
        _record(entry, assignment, status=AdjudicationRecordStatus.ESCALATED)


def test_duplicate_blinded_reviewer_assignment_is_rejected() -> None:
    entry = _entry()
    first = _assignment(entry)
    second = first.model_copy(update={"assignment_id": "assignment.m2006.two"})
    with pytest.raises(ValueError, match="duplicate blinded"):
        AdjudicationRecord.model_validate(
            _record(entry, first).model_copy(update={"assignments": (first, second)}),
            strict=True,
        )


def test_audit_history_must_be_contiguous_and_immutable() -> None:
    entry = _entry()
    assignment = _assignment(entry)
    record = _record(entry, assignment)
    event = record.history[0].model_copy(update={"sequence": 2})
    with pytest.raises(ValueError, match="contiguous"):
        AdjudicationRecord.model_validate(
            record.model_copy(update={"history": (event,)}), strict=True
        )


def test_request_binds_context_upstream_and_source_artifact() -> None:
    request = _request()
    assert request.context.request_id == request.request_id
    assert request.upstream_result.media_type == M2006_M2005_INPUT_MEDIA_TYPE
    with pytest.raises(ValueError, match="upstream workflow result"):
        AdjudicateProteinSubtypeQueueRequest.model_validate(
            request.model_copy(update={"source_artifacts": (_artifact("other"),)}), strict=True
        )
    with pytest.raises(ValueError, match="execution context"):
        AdjudicateProteinSubtypeQueueRequest.model_validate(
            request.model_copy(update={"request_id": "request.m2006.changed"}),
            strict=True,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "9.9.9"),
        ("digest", sha256_digest("m2006:forged-upstream")),
        ("media_type", "application/x-forged-upstream"),
    ],
)
def test_request_requires_full_upstream_artifact_identity(field: str, value: str) -> None:
    request = _request()
    forged_source = request.upstream_result.model_copy(update={field: value})

    with pytest.raises(ValueError, match="upstream workflow result"):
        AdjudicateProteinSubtypeQueueRequest.model_validate(
            request.model_copy(update={"source_artifacts": (forged_source,)}), strict=True
        )


def test_request_rejects_duplicate_reviewer_pair() -> None:
    request = _request()
    duplicate = request.assignments[0].model_copy(update={"assignment_id": "assignment.m2006.two"})
    with pytest.raises(ValueError, match="duplicate blinded"):
        AdjudicateProteinSubtypeQueueRequest.model_validate(
            request.model_copy(update={"assignments": (request.assignments[0], duplicate)}),
            strict=True,
        )


def test_replay_helpers_are_stable_and_detect_tampering() -> None:
    request = _request()
    digest = canonical_request_digest(request)
    assert verify_request_digest(request, digest)
    assert canonical_request_bytes(request) == canonical_request_bytes(request)
    payload = {"result_id": "result.m2006.synthetic", "record": {"status": "resolved"}}
    result_digest = result_payload_digest(payload)
    assert verify_result_digest({**payload, "result_digest": result_digest}, result_digest)
    assert canonical_result_payload_bytes({**payload, "result_digest": result_digest})
    assert not verify_result_digest({**payload, "record": {"status": "tampered"}}, result_digest)


def test_not_evaluable_queue_state_is_explicit() -> None:
    entry = _entry(state=QueueEntryState.NOT_EVALUABLE)
    assignment = _assignment(entry, decision=ReviewDecision.ABSTAIN)
    record = _record(entry, assignment, status=AdjudicationRecordStatus.ESCALATED)
    assert record.entries[0].state is QueueEntryState.NOT_EVALUABLE
