"""Provisional M19-06 reviewer discrepancy and adjudication contracts.

M19-06 owns structured disagreement, blinded review, escalation, resolution,
and immutable history beneath Immunopeptidomic evidence. Unsupported or
unresolved inputs abstain and never become a negative finding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m19_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 6736-6776.
M1906_MODULE_ID: Final = "GLIO-PROTEOGEN-M19-06"
M1906_OPERATION: Final = "adjudicate_proteotype_discrepancy_queue"
M1906_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1906_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-06+json"
M1906_M1905_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-05+json"
M1906_PARENT: Final = "proteotype"
M1906_OWNER: Final = "Platform engineering"
M1906_SAFETY_CLASS: Final = "S2"
M1906_GATE: Final = "G4"
M1906_PROVISIONAL_ABI: Final = True
M1906_MAX_QUEUE_ENTRIES: Final = 256
M1906_MAX_ASSIGNMENTS: Final = 256
M1906_MAX_HISTORY: Final = 1_024
M1906_MAX_EVIDENCE: Final = 64
M1906_MAX_FINDINGS: Final = 64
M1906_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1906_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1906_EVIDENCE_CLAIM: Final = (
    "Caller-declared M19-06 discrepancy, review, escalation and audit material; "
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
    discrepancy_id: Identifier
    reason_code: DiscrepancyReasonCode
    severity: DiscrepancySeverity
    description: NonEmptyStr
    state: QueueEntryState
    blinded_review_required: bool = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1906_MAX_EVIDENCE)


class ReviewerAssignment(FrozenModel):
    assignment_id: Identifier
    discrepancy_id: Identifier
    reviewer_role: NonEmptyStr
    reviewer_token: Identifier
    blinded: Literal[True] = True
    decision: ReviewDecision
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1906_MAX_EVIDENCE)


class ImmutableAuditEvent(FrozenModel):
    sequence: int = Field(ge=1, le=M1906_MAX_HISTORY)
    event_id: Identifier
    event_type: NonEmptyStr
    actor_token: Identifier
    action: NonEmptyStr
    record_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1906_MAX_EVIDENCE)


class AdjudicationRecord(FrozenModel):
    """Versioned queue outcome with immutable history and escalation state."""

    record_id: Identifier
    version: SemanticVersion
    entries: tuple[DiscrepancyQueueEntry, ...] = Field(
        min_length=1, max_length=M1906_MAX_QUEUE_ENTRIES
    )
    assignments: tuple[ReviewerAssignment, ...] = Field(
        min_length=1, max_length=M1906_MAX_ASSIGNMENTS
    )
    history: tuple[ImmutableAuditEvent, ...] = Field(min_length=1, max_length=M1906_MAX_HISTORY)
    status: AdjudicationRecordStatus
    resolution_summary: NonEmptyStr | None = None
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1906_MAX_EVIDENCE)

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
        known_entries = set(entry_ids)
        if any(item.discrepancy_id not in known_entries for item in self.assignments):
            raise ValueError("assignment references an unknown discrepancy")
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
    maximum_queue_entries: int = Field(gt=0, le=M1906_MAX_QUEUE_ENTRIES)
    escalation_required_for_critical: Literal[True] = True
    immutable_history_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1906_MAX_EVIDENCE)


class QueueFinding(FrozenModel):
    finding_id: Identifier
    code: QueueFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1906_MAX_EVIDENCE)


class AdjudicateProteotypeQueueRequest(FrozenModel):
    """Provisional request bound to the M19-05 workflow object."""

    operation: Literal["adjudicate_proteotype_discrepancy_queue"] = M1906_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1906_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    entries: tuple[DiscrepancyQueueEntry, ...] = Field(
        min_length=1, max_length=M1906_MAX_QUEUE_ENTRIES
    )
    assignments: tuple[ReviewerAssignment, ...] = Field(
        min_length=1, max_length=M1906_MAX_ASSIGNMENTS
    )
    configuration: ReviewWorkspaceConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1906_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdjudicateProteotypeQueueRequest:
        if self.upstream_result.media_type != M1906_M1905_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M19-05 workflow result")
        entry_ids = tuple(item.discrepancy_id for item in self.entries)
        assignment_ids = tuple(item.assignment_id for item in self.assignments)
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("request discrepancy ids must be unique")
        if len(assignment_ids) != len(set(assignment_ids)):
            raise ValueError("request assignment ids must be unique")
        allowed = set(entry_ids)
        if any(item.discrepancy_id not in allowed for item in self.assignments):
            raise ValueError("request assignment references an unknown discrepancy")
        return self


class ProteotypeAdjudicationResult(FrozenModel):
    """Versioned adjudication record with safe abstention and audit history."""

    output_type: Literal["proteotype_adjudication"] = "proteotype_adjudication"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1906_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateProteotypeQueueRequest
    status: QueueResultStatus
    record: AdjudicationRecord | None = None
    findings: tuple[QueueFinding, ...] = Field(default=(), max_length=M1906_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1906_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1906_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeAdjudicationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.status is QueueResultStatus.RECORDED:
            if (
                self.record is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("recorded result requires a supported immutable record")
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
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1906_CONTRACT_VERSION",
    "M1906_EVIDENCE_CLAIM",
    "M1906_GATE",
    "M1906_M1905_INPUT_MEDIA_TYPE",
    "M1906_MAX_ASSIGNMENTS",
    "M1906_MAX_CANONICAL_REQUEST_BYTES",
    "M1906_MAX_CANONICAL_RESULT_BYTES",
    "M1906_MAX_EVIDENCE",
    "M1906_MAX_FINDINGS",
    "M1906_MAX_HISTORY",
    "M1906_MAX_QUEUE_ENTRIES",
    "M1906_MODULE_ID",
    "M1906_OPERATION",
    "M1906_OUTPUT_MEDIA_TYPE",
    "M1906_OWNER",
    "M1906_PARENT",
    "M1906_PROVISIONAL_ABI",
    "M1906_SAFETY_CLASS",
    "AdjudicateProteotypeQueueRequest",
    "AdjudicationRecord",
    "AdjudicationRecordStatus",
    "DiscrepancyQueueEntry",
    "DiscrepancyReasonCode",
    "DiscrepancySeverity",
    "ImmutableAuditEvent",
    "ProteotypeAdjudicationResult",
    "QueueEntryState",
    "QueueFinding",
    "QueueFindingCode",
    "QueueResultStatus",
    "ReviewDecision",
    "ReviewWorkspaceConfiguration",
    "ReviewerAssignment",
]
