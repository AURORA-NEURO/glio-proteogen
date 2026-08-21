"""Adversarial contract closure tests for provisional M17-06."""

# ruff: noqa: S106

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m17_06 import (
    AdjudicateVariantPeptideDiscrepancyQueueRequest,
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
    VariantPeptideAdjudicationResult,
    canonical_request_digest,
    result_payload_digest,
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_06_reviewer_discrepancy_adjudication as m1706,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1706": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="M17-06 caller-declared adjudication evidence",
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id="request.m1706",
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("intended"),
            ),
        ),
    )


def _entry(
    discrepancy_id: str = "discrepancy.001",
    *,
    severity: DiscrepancySeverity = DiscrepancySeverity.CRITICAL,
    state: QueueEntryState = QueueEntryState.RESOLVED,
) -> DiscrepancyQueueEntry:
    return DiscrepancyQueueEntry(
        discrepancy_id=discrepancy_id,
        reason_code=DiscrepancyReasonCode.SOURCE_DISAGREEMENT,
        severity=severity,
        description="Protein and genomic evidence require adjudication.",
        state=state,
        evidence=(_evidence(discrepancy_id),),
    )


def _assignment(
    discrepancy_id: str = "discrepancy.001",
    *,
    decision: ReviewDecision = ReviewDecision.ACCEPT,
) -> ReviewerAssignment:
    return ReviewerAssignment(
        assignment_id=f"assignment.{discrepancy_id.removeprefix('discrepancy.')}",
        discrepancy_id=discrepancy_id,
        reviewer_role="clinical_reviewer",
        reviewer_token="reviewer.opaque.001",
        decision=decision,
        rationale="Evidence was reviewed under the declared queue policy.",
        evidence=(_evidence(f"assignment.{discrepancy_id}"),),
    )


def _record(
    entry: DiscrepancyQueueEntry | None = None,
    assignment: ReviewerAssignment | None = None,
    *,
    status: AdjudicationRecordStatus = AdjudicationRecordStatus.RESOLVED,
    sequence: int = 1,
) -> AdjudicationRecord:
    actual_entry = entry or _entry()
    actual_assignment = assignment or _assignment(actual_entry.discrepancy_id)
    return AdjudicationRecord(
        record_id="record.m1706.001",
        version="1.0.0",
        entries=(actual_entry,),
        assignments=(actual_assignment,),
        history=(
            ImmutableAuditEvent(
                sequence=sequence,
                event_id="event.m1706.001",
                event_type="review_resolution",
                actor_token="reviewer.opaque.001",
                action="resolved discrepancy",
                record_digest=sha256_digest("record.m1706.001"),
                evidence=(_evidence("event.001"),),
            ),
        ),
        status=status,
        resolution_summary=(
            "Critical discrepancy was resolved with an immutable review history."
            if status is AdjudicationRecordStatus.RESOLVED
            else None
        ),
        evidence=(_evidence("record"),),
    )


def _configuration() -> ReviewWorkspaceConfiguration:
    return ReviewWorkspaceConfiguration(
        configuration_id="configuration.m1706",
        version="1.0.0",
        maximum_queue_entries=16,
        evidence=(_evidence("configuration"),),
    )


def _request(
    entries: tuple[DiscrepancyQueueEntry, ...] = (_entry(),),
    assignments: tuple[ReviewerAssignment, ...] = (_assignment(),),
) -> AdjudicateVariantPeptideDiscrepancyQueueRequest:
    return AdjudicateVariantPeptideDiscrepancyQueueRequest(
        request_id="request.m1706",
        context=_context(),
        upstream_result=_artifact(
            "m1705-workspace", media_type="application/vnd.glio-proteogen.m17-05+json"
        ),
        entries=entries,
        assignments=assignments,
        configuration=_configuration(),
        source_artifacts=(_artifact("proteome"), _artifact("genome"), _artifact("ptm")),
    )


def test_request_requires_complete_blinded_assignments() -> None:
    with pytest.raises(ValidationError, match="one assignment for every discrepancy"):
        _request(
            entries=(_entry(), _entry("discrepancy.002")),
            assignments=(_assignment(),),
        )
    with pytest.raises(ValidationError, match="blinded"):
        _request(assignments=(_assignment().model_copy(update={"blinded": False}),))


def test_record_requires_ordered_history_and_closed_critical_review() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        _record(sequence=2)
    with pytest.raises(ValidationError, match="final review decision"):
        _record(assignment=_assignment(decision=ReviewDecision.DEFER))
    with pytest.raises(ValidationError, match="resolved"):
        _record(entry=_entry(state=QueueEntryState.IN_REVIEW))


def test_escalated_record_requires_unresolved_entry_and_no_summary() -> None:
    record = _record(
        entry=_entry(state=QueueEntryState.ESCALATED),
        status=AdjudicationRecordStatus.ESCALATED,
    )
    assert record.resolution_summary is None
    with pytest.raises(ValidationError, match="unresolved"):
        _record(status=AdjudicationRecordStatus.ESCALATED)


def test_request_binds_m17_05_media_type_and_configuration_limits() -> None:
    with pytest.raises(ValidationError, match="M17-05"):
        AdjudicateVariantPeptideDiscrepancyQueueRequest.model_validate(
            _request().model_dump(mode="python")
            | {"upstream_result": _artifact("wrong", media_type="application/json")}
        )
    with pytest.raises(ValidationError):
        ReviewWorkspaceConfiguration.model_validate(
            _configuration().model_dump(mode="python") | {"maximum_queue_entries": 0}
        )


def test_record_rejects_duplicate_unknown_and_incomplete_membership() -> None:
    with pytest.raises(ValidationError, match="discrepancy ids must be unique"):
        AdjudicationRecord.model_validate(
            _record().model_dump(mode="python") | {"entries": (_entry(), _entry())}
        )
    duplicate = _assignment().model_copy(update={"assignment_id": "assignment.001"})
    with pytest.raises(ValidationError, match="assignment ids must be unique"):
        AdjudicationRecord.model_validate(
            _record().model_dump(mode="python") | {"assignments": (_assignment(), duplicate)}
        )
    with pytest.raises(ValidationError, match="unknown discrepancy"):
        AdjudicationRecord.model_validate(
            _record().model_dump(mode="python")
            | {"assignments": (_assignment("discrepancy.unknown"),)}
        )
    with pytest.raises(ValidationError, match="every discrepancy"):
        AdjudicationRecord.model_validate(
            _record().model_dump(mode="python") | {"entries": (_entry(), _entry("discrepancy.002"))}
        )


def test_record_rejects_duplicate_history_and_request_identity_collisions() -> None:
    record_data = _record().model_dump(mode="python")
    event = _record().history[0]
    with pytest.raises(ValidationError, match="audit event ids"):
        AdjudicationRecord.model_validate(record_data | {"history": (event, event)})
    with pytest.raises(ValidationError, match="request discrepancy ids"):
        AdjudicateVariantPeptideDiscrepancyQueueRequest.model_validate(
            _request().model_dump(mode="python")
            | {"entries": (_entry(), _entry()), "assignments": (_assignment(), _assignment())}
        )
    with pytest.raises(ValidationError, match="request assignment ids"):
        AdjudicateVariantPeptideDiscrepancyQueueRequest.model_validate(
            _request().model_dump(mode="python")
            | {
                "entries": (_entry(), _entry("discrepancy.002")),
                "assignments": (
                    _assignment(),
                    _assignment("discrepancy.002").model_copy(
                        update={"assignment_id": "assignment.001"}
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="request assignment references"):
        AdjudicateVariantPeptideDiscrepancyQueueRequest.model_validate(
            _request().model_dump(mode="python")
            | {"assignments": (_assignment("discrepancy.unknown"),)}
        )


def test_record_requires_resolution_summary_and_escalation_semantics() -> None:
    with pytest.raises(ValidationError, match="resolution summary"):
        AdjudicationRecord.model_validate(
            _record().model_dump(mode="python") | {"resolution_summary": None}
        )
    escalated = _record(
        entry=_entry(state=QueueEntryState.ESCALATED),
        status=AdjudicationRecordStatus.ESCALATED,
    )
    with pytest.raises(ValidationError, match="cannot claim"):
        AdjudicationRecord.model_validate(
            escalated.model_dump(mode="python") | {"resolution_summary": "claimed"}
        )


def test_canonical_projections_accept_mapping_and_result_closure_is_strict() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
    result_payload = {
        "result_id": "result.example",
        "result_digest": "sha256:" + "a" * 64,
    }
    assert result_payload_digest(result_payload).startswith("sha256:")
    result = m1706.M1706AdjudicationEngine().export(request)
    with pytest.raises(ValidationError, match="request digest"):
        VariantPeptideAdjudicationResult.model_validate(
            result.model_dump(mode="python") | {"request_digest": "sha256:" + "b" * 64}
        )
    with pytest.raises(ValidationError, match="always requires"):
        VariantPeptideAdjudicationResult.model_validate(
            result.model_dump(mode="python") | {"human_review_required": False}
        )
    assert result_payload_digest(result) == result.result_digest


def test_result_closure_rejects_record_status_membership_and_abstention_mutations() -> None:
    result = m1706.M1706AdjudicationEngine().export(_request())
    escalated = _record(
        entry=_entry(state=QueueEntryState.ESCALATED),
        status=AdjudicationRecordStatus.ESCALATED,
    )
    with pytest.raises(ValidationError, match="resolved record"):
        VariantPeptideAdjudicationResult.model_validate(
            result.model_dump(mode="python") | {"record": escalated}
        )
    mismatched = _record(entry=_entry("discrepancy.other"))
    with pytest.raises(ValidationError, match="every requested"):
        VariantPeptideAdjudicationResult.model_validate(
            result.model_dump(mode="python") | {"record": mismatched}
        )
    with pytest.raises(ValidationError, match="review-only immutable"):
        VariantPeptideAdjudicationResult.model_validate(
            result.model_dump(mode="python")
            | {
                "record": None,
                "support_decision": result.support_decision.model_copy(
                    update={"status": SupportStatus.REVIEW_REQUIRED}
                ),
            }
        )
    review = m1706.M1706AdjudicationEngine().export(
        _request(
            entries=(_entry(state=QueueEntryState.IN_REVIEW),),
            assignments=(_assignment(decision=ReviewDecision.DEFER),),
        )
    )
    with pytest.raises(ValidationError, match="safe status"):
        VariantPeptideAdjudicationResult.model_validate(
            review.model_dump(mode="python")
            | {
                "support_decision": result.support_decision.model_copy(
                    update={"status": SupportStatus.SUPPORTED}
                )
            }
        )
