"""Provisional M17-06 reviewer discrepancy and adjudication contracts.

M17-06 owns a structured discrepancy queue, blinded review, escalation,
resolution and immutable history beneath the KINOPHOS object consumer.  The
public ABI is provisional pending Clinical science owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m17_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from the M17-06 dossier slice.
M1706_MODULE_ID: Final = "GLIO-PROTEOGEN-M17-06"
M1706_OPERATION: Final = "adjudicate_variant_peptide_discrepancy_queue"
M1706_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1706_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m17-06+json"
M1706_M1705_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m17-05+json"
M1706_PARENT: Final = "variant peptide"
M1706_OWNER: Final = "Clinical science"
M1706_SAFETY_CLASS: Final = "S2"
M1706_GATE: Final = "G4"
M1706_PROVISIONAL_ABI: Final = True
M1706_MAX_QUEUE_ENTRIES: Final = 256
M1706_MAX_ASSIGNMENTS: Final = 256
M1706_MAX_HISTORY: Final = 1_024
M1706_MAX_EVIDENCE: Final = 64
M1706_MAX_FINDINGS: Final = 64
M1706_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1706_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1706_EVIDENCE_CLAIM: Final = (
    "Caller-declared M17-06 discrepancy, review, escalation and audit material; "
    "issuer authority is not authenticated."
)


class DiscrepancyReasonCode(StrEnum):
    SOURCE_DISAGREEMENT = "source_disagreement"
    MISSING_EVIDENCE = "missing_evidence"
    IDENTITY_CONFLICT = "identity_conflict"
    QUALITY_FAILURE = "quality_failure"
    SUPPORT_BOUNDARY = "support_boundary"
    PROVENANCE_GAP = "provenance_gap"
    OTHER = "other"


class DiscrepancySeverity(StrEnum):
    CRITICAL = "critical"
    MATERIAL = "material"
    ROUTINE = "routine"


class QueueEntryState(StrEnum):
    QUEUED = "queued"
    IN_REVIEW = "in_review"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    NOT_EVALUABLE = "not_evaluable"


class ReviewDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"
    ABSTAIN = "abstain"


class AdjudicationRecordStatus(StrEnum):
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class QueueResultStatus(StrEnum):
    RECORDED = "recorded"
    ABSTAINED = "abstained"


class QueueFindingCode(StrEnum):
    REVIEW_REQUIRED = "review_required"
    CRITICAL_UNRESOLVED = "critical_unresolved"
    ASSIGNMENT_MISSING = "assignment_missing"
    HISTORY_INCOMPLETE = "history_incomplete"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class DiscrepancyQueueEntry(FrozenModel):
    """One typed discrepancy routed for human review."""

    discrepancy_id: Identifier
    reason_code: DiscrepancyReasonCode
    severity: DiscrepancySeverity
    description: NonEmptyStr
    state: QueueEntryState
    blinded_review_required: bool = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1706_MAX_EVIDENCE)


class ReviewerAssignment(FrozenModel):
    """A review assignment addressed by an opaque reviewer token."""

    assignment_id: Identifier
    discrepancy_id: Identifier
    reviewer_role: NonEmptyStr
    reviewer_token: Identifier
    blinded: Literal[True] = True
    decision: ReviewDecision
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1706_MAX_EVIDENCE)


class ImmutableAuditEvent(FrozenModel):
    """Append-only event in the adjudication history."""

    sequence: int = Field(ge=1, le=M1706_MAX_HISTORY)
    event_id: Identifier
    event_type: NonEmptyStr
    actor_token: Identifier
    action: NonEmptyStr
    record_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1706_MAX_EVIDENCE)


class AdjudicationRecord(FrozenModel):
    """Versioned queue outcome with immutable history and escalation state."""

    record_id: Identifier
    version: SemanticVersion
    entries: tuple[DiscrepancyQueueEntry, ...] = Field(
        min_length=1, max_length=M1706_MAX_QUEUE_ENTRIES
    )
    assignments: tuple[ReviewerAssignment, ...] = Field(
        min_length=1, max_length=M1706_MAX_ASSIGNMENTS
    )
    history: tuple[ImmutableAuditEvent, ...] = Field(min_length=1, max_length=M1706_MAX_HISTORY)
    status: AdjudicationRecordStatus
    resolution_summary: NonEmptyStr | None = None
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1706_MAX_EVIDENCE)

    @model_validator(mode="after")
    def record_is_closed(self) -> AdjudicationRecord:
        entry_ids = tuple(item.discrepancy_id for item in self.entries)
        assignment_ids = tuple(item.assignment_id for item in self.assignments)
        event_ids = tuple(item.event_id for item in self.history)
        sequences = tuple(item.sequence for item in self.history)
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("discrepancy ids must be unique")
        if len(assignment_ids) != len(set(assignment_ids)):
            raise ValueError("assignment ids must be unique")
        if len(event_ids) != len(set(event_ids)) or len(sequences) != len(set(sequences)):
            raise ValueError("audit event ids and sequence numbers must be unique")
        if sequences != tuple(range(1, len(sequences) + 1)):
            raise ValueError("audit history must be contiguous and ordered")
        known_entries = set(entry_ids)
        if any(item.discrepancy_id not in known_entries for item in self.assignments):
            raise ValueError("assignment references an unknown discrepancy")
        assigned_entries = {item.discrepancy_id for item in self.assignments}
        if assigned_entries != known_entries:
            raise ValueError("every discrepancy requires an assignment")
        if any(item.blinded is not True for item in self.assignments):
            raise ValueError("all reviewer assignments must remain blinded")
        if self.status is AdjudicationRecordStatus.RESOLVED and any(
            item.state is not QueueEntryState.RESOLVED for item in self.entries
        ):
            raise ValueError("resolved record requires every entry to be resolved")
        if self.status is AdjudicationRecordStatus.ESCALATED and all(
            item.state is QueueEntryState.RESOLVED for item in self.entries
        ):
            raise ValueError("escalated record requires an unresolved entry")
        critical_ids = {
            item.discrepancy_id
            for item in self.entries
            if item.severity is DiscrepancySeverity.CRITICAL
        }
        if self.status is AdjudicationRecordStatus.RESOLVED and any(
            item.decision not in {ReviewDecision.ACCEPT, ReviewDecision.REJECT}
            for item in self.assignments
            if item.discrepancy_id in critical_ids
        ):
            raise ValueError("critical resolved entries require a final review decision")
        if self.status is AdjudicationRecordStatus.RESOLVED and self.resolution_summary is None:
            raise ValueError("resolved record requires a resolution summary")
        if (
            self.status is AdjudicationRecordStatus.ESCALATED
            and self.resolution_summary is not None
        ):
            raise ValueError("escalated record cannot claim final resolution")
        return self


class ReviewWorkspaceConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    maximum_queue_entries: int = Field(gt=0, le=M1706_MAX_QUEUE_ENTRIES)
    escalation_required_for_critical: Literal[True] = True
    immutable_history_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1706_MAX_EVIDENCE)


class QueueFinding(FrozenModel):
    finding_id: Identifier
    code: QueueFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1706_MAX_EVIDENCE)


class AdjudicateVariantPeptideDiscrepancyQueueRequest(FrozenModel):
    """Provisional request bound to the M17-05 workspace object."""

    operation: Literal["adjudicate_variant_peptide_discrepancy_queue"] = M1706_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1706_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    entries: tuple[DiscrepancyQueueEntry, ...] = Field(
        min_length=1, max_length=M1706_MAX_QUEUE_ENTRIES
    )
    assignments: tuple[ReviewerAssignment, ...] = Field(
        min_length=1, max_length=M1706_MAX_ASSIGNMENTS
    )
    configuration: ReviewWorkspaceConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1706_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdjudicateVariantPeptideDiscrepancyQueueRequest:
        if self.upstream_result.media_type != M1706_M1705_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M17-05 workspace result")
        entry_ids = tuple(item.discrepancy_id for item in self.entries)
        assignment_ids = tuple(item.assignment_id for item in self.assignments)
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("request discrepancy ids must be unique")
        if len(assignment_ids) != len(set(assignment_ids)):
            raise ValueError("request assignment ids must be unique")
        allowed = set(entry_ids)
        if any(item.discrepancy_id not in allowed for item in self.assignments):
            raise ValueError("request assignment references an unknown discrepancy")
        if {item.discrepancy_id for item in self.assignments} != allowed:
            raise ValueError("request requires one assignment for every discrepancy")
        if any(item.blinded is not True for item in self.assignments):
            raise ValueError("request reviewer assignments must remain blinded")
        return self


class VariantPeptideAdjudicationResult(FrozenModel):
    """Versioned adjudication record with safe abstention and audit history."""

    output_type: Literal["variant_peptide_adjudication"] = "variant_peptide_adjudication"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1706_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateVariantPeptideDiscrepancyQueueRequest
    status: QueueResultStatus
    record: AdjudicationRecord | None = None
    findings: tuple[QueueFinding, ...] = Field(default=(), max_length=M1706_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant peptide"] = M1706_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1706_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideAdjudicationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is QueueResultStatus.RECORDED:
            if (
                self.record is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("recorded result requires a supported immutable record")
            if self.record.status is not AdjudicationRecordStatus.RESOLVED:
                raise ValueError("recorded result requires a resolved record")
            request_ids = {item.discrepancy_id for item in self.request.entries}
            record_ids = {item.discrepancy_id for item in self.record.entries}
            if request_ids != record_ids:
                raise ValueError("record must include every requested discrepancy")
        elif (
            self.record is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no record and safe status")
        if not self.human_review_required:
            raise ValueError("M17-06 always requires human review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1706_CONTRACT_VERSION",
    "M1706_EVIDENCE_CLAIM",
    "M1706_GATE",
    "M1706_M1705_INPUT_MEDIA_TYPE",
    "M1706_MAX_ASSIGNMENTS",
    "M1706_MAX_CANONICAL_REQUEST_BYTES",
    "M1706_MAX_CANONICAL_RESULT_BYTES",
    "M1706_MAX_EVIDENCE",
    "M1706_MAX_FINDINGS",
    "M1706_MAX_HISTORY",
    "M1706_MAX_QUEUE_ENTRIES",
    "M1706_MODULE_ID",
    "M1706_OPERATION",
    "M1706_OUTPUT_MEDIA_TYPE",
    "M1706_OWNER",
    "M1706_PARENT",
    "M1706_PROVISIONAL_ABI",
    "M1706_SAFETY_CLASS",
    "AdjudicateVariantPeptideDiscrepancyQueueRequest",
    "AdjudicationRecord",
    "AdjudicationRecordStatus",
    "DiscrepancyQueueEntry",
    "DiscrepancyReasonCode",
    "DiscrepancySeverity",
    "ImmutableAuditEvent",
    "QueueEntryState",
    "QueueFinding",
    "QueueFindingCode",
    "QueueResultStatus",
    "ReviewDecision",
    "ReviewWorkspaceConfiguration",
    "ReviewerAssignment",
    "VariantPeptideAdjudicationResult",
]
