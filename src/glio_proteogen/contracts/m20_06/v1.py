"""Provisional M20-06 reviewer discrepancy and adjudication contracts.

M20-06 owns structured disagreement, blinded review, escalation, resolution,
and immutable history beneath Biomarker-panel translation. Unsupported or
unresolved inputs abstain and never become a negative finding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m20_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 7096-7136.
M2006_MODULE_ID: Final = "GLIO-PROTEOGEN-M20-06"
M2006_OPERATION: Final = "adjudicate_protein_subtype_discrepancy_queue"
M2006_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2006_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-06+json"
M2006_M2005_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-05+json"
M2006_PARENT: Final = "protein subtype"
M2006_OWNER: Final = "Scientific engineering"
M2006_SAFETY_CLASS: Final = "S2"
M2006_GATE: Final = "G4"
M2006_PROVISIONAL_ABI: Final = True
M2006_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2006_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7096-7136"
M2006_MAX_QUEUE_ENTRIES: Final = 256
M2006_MAX_ASSIGNMENTS: Final = 256
M2006_MAX_HISTORY: Final = 1_024
M2006_MAX_EVIDENCE: Final = 64
M2006_MAX_FINDINGS: Final = 64
M2006_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2006_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2006_EVIDENCE_CLAIM: Final = (
    "Caller-declared M20-06 discrepancy, review, escalation and audit material; "
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
    blinded_review_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2006_MAX_EVIDENCE)


class ReviewerAssignment(FrozenModel):
    assignment_id: Identifier
    discrepancy_id: Identifier
    reviewer_role: NonEmptyStr
    reviewer_token: Identifier
    blinded: Literal[True] = True
    decision: ReviewDecision
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2006_MAX_EVIDENCE)


class ImmutableAuditEvent(FrozenModel):
    sequence: int = Field(ge=1, le=M2006_MAX_HISTORY)
    event_id: Identifier
    event_type: NonEmptyStr
    actor_token: Identifier
    action: NonEmptyStr
    record_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2006_MAX_EVIDENCE)


class AdjudicationRecord(FrozenModel):
    """Versioned queue outcome with immutable history and escalation state."""

    record_id: Identifier
    version: SemanticVersion
    entries: tuple[DiscrepancyQueueEntry, ...] = Field(
        min_length=1, max_length=M2006_MAX_QUEUE_ENTRIES
    )
    assignments: tuple[ReviewerAssignment, ...] = Field(
        min_length=1, max_length=M2006_MAX_ASSIGNMENTS
    )
    history: tuple[ImmutableAuditEvent, ...] = Field(min_length=1, max_length=M2006_MAX_HISTORY)
    status: AdjudicationRecordStatus
    resolution_summary: NonEmptyStr | None = None
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2006_MAX_EVIDENCE)

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
            raise ValueError("audit history sequences must be contiguous from one")
        known_entries = set(entry_ids)
        if any(item.discrepancy_id not in known_entries for item in self.assignments):
            raise ValueError("assignment references an unknown discrepancy")
        assignment_keys = tuple(
            (item.discrepancy_id, item.reviewer_token) for item in self.assignments
        )
        if len(assignment_keys) != len(set(assignment_keys)):
            raise ValueError("duplicate blinded reviewer assignment")
        if self.status is AdjudicationRecordStatus.RESOLVED and self.resolution_summary is None:
            raise ValueError("resolved record requires a resolution summary")
        if self.status is AdjudicationRecordStatus.RESOLVED:
            if any(item.state is not QueueEntryState.RESOLVED for item in self.entries):
                raise ValueError("resolved record requires every entry to be resolved")
            if any(
                item.decision not in {ReviewDecision.ACCEPT, ReviewDecision.REJECT}
                for item in self.assignments
            ):
                raise ValueError("resolved record cannot contain deferred or abstained decisions")
        if (
            self.status is AdjudicationRecordStatus.ESCALATED
            and self.resolution_summary is not None
        ):
            raise ValueError("escalated record cannot claim final resolution")
        if self.status is AdjudicationRecordStatus.ESCALATED and not any(
            item.state in {QueueEntryState.ESCALATED, QueueEntryState.NOT_EVALUABLE}
            for item in self.entries
        ):
            raise ValueError("escalated record requires an escalated or non-evaluable entry")
        return self


class ReviewWorkspaceConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    maximum_queue_entries: int = Field(gt=0, le=M2006_MAX_QUEUE_ENTRIES)
    escalation_required_for_critical: Literal[True] = True
    immutable_history_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2006_MAX_EVIDENCE)


class QueueFinding(FrozenModel):
    finding_id: Identifier
    code: QueueFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2006_MAX_EVIDENCE)


class AdjudicateProteinSubtypeQueueRequest(FrozenModel):
    """Provisional request bound to the M20-05 workflow object."""

    operation: Literal["adjudicate_protein_subtype_discrepancy_queue"] = M2006_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2006_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    entries: tuple[DiscrepancyQueueEntry, ...] = Field(
        min_length=1, max_length=M2006_MAX_QUEUE_ENTRIES
    )
    assignments: tuple[ReviewerAssignment, ...] = Field(
        min_length=1, max_length=M2006_MAX_ASSIGNMENTS
    )
    configuration: ReviewWorkspaceConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2006_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdjudicateProteinSubtypeQueueRequest:
        if self.upstream_result.media_type != M2006_M2005_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M20-05 workflow result")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        entry_ids = tuple(item.discrepancy_id for item in self.entries)
        assignment_ids = tuple(item.assignment_id for item in self.assignments)
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("request discrepancy ids must be unique")
        if len(assignment_ids) != len(set(assignment_ids)):
            raise ValueError("request assignment ids must be unique")
        allowed = set(entry_ids)
        if any(item.discrepancy_id not in allowed for item in self.assignments):
            raise ValueError("request assignment references an unknown discrepancy")
        assignment_keys = tuple(
            (item.discrepancy_id, item.reviewer_token) for item in self.assignments
        )
        if len(assignment_keys) != len(set(assignment_keys)):
            raise ValueError("request contains duplicate blinded reviewer assignments")
        artifact_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(artifact_keys) != len(set(artifact_keys)):
            raise ValueError("request source artifacts must be unique by full identity")
        upstream_key = (
            self.upstream_result.artifact_id,
            self.upstream_result.version,
            self.upstream_result.digest,
            self.upstream_result.media_type,
        )
        if upstream_key not in set(artifact_keys):
            raise ValueError("request source artifacts must include the upstream workflow result")
        return self


class ProteinSubtypeAdjudicationResult(FrozenModel):
    """Versioned adjudication record with safe abstention and audit history."""

    output_type: Literal["protein_subtype_adjudication"] = "protein_subtype_adjudication"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2006_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateProteinSubtypeQueueRequest
    status: QueueResultStatus
    record: AdjudicationRecord | None = None
    findings: tuple[QueueFinding, ...] = Field(default=(), max_length=M2006_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2006_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2006_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeAdjudicationResult:
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
            request_assignment_ids = {item.assignment_id for item in self.request.assignments}
            record_assignment_ids = {item.assignment_id for item in self.record.assignments}
            if request_assignment_ids != record_assignment_ids:
                raise ValueError("record must preserve every reviewer assignment")
        elif (
            self.record is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no record and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("queue finding ids must be unique")
        return self


__all__ = [
    "M2006_CONTRACT_VERSION",
    "M2006_DOSSIER_SHA256",
    "M2006_DOSSIER_SLICE",
    "M2006_EVIDENCE_CLAIM",
    "M2006_GATE",
    "M2006_M2005_INPUT_MEDIA_TYPE",
    "M2006_MAX_ASSIGNMENTS",
    "M2006_MAX_CANONICAL_REQUEST_BYTES",
    "M2006_MAX_CANONICAL_RESULT_BYTES",
    "M2006_MAX_EVIDENCE",
    "M2006_MAX_FINDINGS",
    "M2006_MAX_HISTORY",
    "M2006_MAX_QUEUE_ENTRIES",
    "M2006_MODULE_ID",
    "M2006_OPERATION",
    "M2006_OUTPUT_MEDIA_TYPE",
    "M2006_OWNER",
    "M2006_PARENT",
    "M2006_PROVISIONAL_ABI",
    "M2006_SAFETY_CLASS",
    "AdjudicateProteinSubtypeQueueRequest",
    "AdjudicationRecord",
    "AdjudicationRecordStatus",
    "DiscrepancyQueueEntry",
    "DiscrepancyReasonCode",
    "DiscrepancySeverity",
    "ImmutableAuditEvent",
    "ProteinSubtypeAdjudicationResult",
    "QueueEntryState",
    "QueueFinding",
    "QueueFindingCode",
    "QueueResultStatus",
    "ReviewDecision",
    "ReviewWorkspaceConfiguration",
    "ReviewerAssignment",
]
