"""Provisional M20-05 workflow presentation service contracts.

The dossier requires task-specific views, evidence summaries, uncertainty,
discrepancies, provenance, and safe default ordering.  The ABI is provisional;
this service presents a human-review workspace and never converts unsupported
evidence into a negative finding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m20_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 7052-7092.
M2005_MODULE_ID: Final = "GLIO-PROTEOGEN-M20-05"
M2005_OPERATION: Final = "present_protein_subtype_human_review_workspace"
M2005_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2005_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-05+json"
M2005_M2004_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-04+json"
M2005_PARENT: Final = "protein subtype"
M2005_OWNER: Final = "Platform engineering"
M2005_SAFETY_CLASS: Final = "S2"
M2005_GATE: Final = "G4"
M2005_PROVISIONAL_ABI: Final = True
M2005_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2005_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7052-7092"
M2005_MAX_ITEMS: Final = 256
M2005_MAX_EVIDENCE: Final = 64
M2005_MAX_DISCREPANCIES: Final = 128
M2005_MAX_ACTIONS: Final = 64
M2005_MAX_FINDINGS: Final = 64
M2005_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2005_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class ViewKind(StrEnum):
    TASK_SUMMARY = "task_summary"
    EVIDENCE_REVIEW = "evidence_review"
    UNCERTAINTY = "uncertainty"
    DISCREPANCY = "discrepancy"
    PROVENANCE = "provenance"
    NEXT_ACTION = "next_action"


class OrderingPolicy(StrEnum):
    SAFE_DEFAULT = "safe_default"
    REVIEW_PRIORITY = "review_priority"
    UNCERTAINTY_FIRST = "uncertainty_first"


class ReviewItemStatus(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    CONFLICTED = "conflicted"
    UNRESOLVED = "unresolved"
    ABSTAINED = "abstained"


class WorkspaceStatus(StrEnum):
    PRESENTED = "presented"
    ABSTAINED = "abstained"


class WorkflowFindingCode(StrEnum):
    MISSING_EVIDENCE_SUMMARY = "missing_evidence_summary"
    DISCREPANCY_REQUIRES_REVIEW = "discrepancy_requires_review"
    AUTOMATION_BIAS_GUARD = "automation_bias_guard"
    PROVENANCE_REQUIRED = "provenance_required"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


_REQUIRED_VIEWS: Final = frozenset(ViewKind)


class PresentationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    automation_bias_guard_required: Literal[True] = True
    safe_default_order_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2005_MAX_EVIDENCE)


class PresentationPolicy(FrozenModel):
    required_views: tuple[ViewKind, ...] = Field(min_length=1, max_length=8)
    default_ordering: OrderingPolicy = OrderingPolicy.SAFE_DEFAULT
    maximum_items: int = Field(ge=1, le=M2005_MAX_ITEMS)
    uncertainty_required: Literal[True] = True
    discrepancy_review_required: Literal[True] = True
    provenance_required: Literal[True] = True
    configuration: PresentationConfiguration

    @model_validator(mode="after")
    def required_views_are_unique(self) -> PresentationPolicy:
        if len(set(self.required_views)) != len(self.required_views):
            raise ValueError("required workspace views must be unique")
        if set(self.required_views) != _REQUIRED_VIEWS:
            raise ValueError("policy must require every safety-critical workspace view")
        return self


class NextAction(FrozenModel):
    action_id: Identifier
    label: NonEmptyStr
    rationale: NonEmptyStr
    required_evidence: tuple[ArtifactReference, ...] = Field(
        default=(), max_length=M2005_MAX_EVIDENCE
    )
    review_only: Literal[True] = True


class ReviewItem(FrozenModel):
    item_id: Identifier
    view_kind: ViewKind
    title: NonEmptyStr
    position: int = Field(ge=0, le=M2005_MAX_ITEMS)
    status: ReviewItemStatus
    evidence_summary: NonEmptyStr
    uncertainty_summary: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2005_MAX_EVIDENCE)
    discrepancy_ids: tuple[Identifier, ...] = Field(default=(), max_length=M2005_MAX_DISCREPANCIES)
    provenance_artifact: ArtifactReference
    next_action: NextAction | None = None

    @model_validator(mode="after")
    def review_escalation_is_explicit(self) -> ReviewItem:
        if self.status in {
            ReviewItemStatus.CONFLICTED,
            ReviewItemStatus.UNRESOLVED,
            ReviewItemStatus.ABSTAINED,
        } and (not self.discrepancy_ids or self.next_action is None):
            raise ValueError("review escalation requires a discrepancy and next action")
        return self


class HumanReviewWorkspace(FrozenModel):
    workspace_id: Identifier
    version: SemanticVersion
    parent_target: Literal["protein subtype"] = M2005_PARENT
    items: tuple[ReviewItem, ...] = Field(min_length=1, max_length=M2005_MAX_ITEMS)
    ordering: OrderingPolicy
    safe_default_order: Literal[True] = True
    automation_bias_warning: NonEmptyStr
    source_bundle: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2005_MAX_EVIDENCE)

    @model_validator(mode="after")
    def items_are_unique_and_ordered(self) -> HumanReviewWorkspace:
        ids = tuple(item.item_id for item in self.items)
        positions = tuple(item.position for item in self.items)
        if len(ids) != len(set(ids)):
            raise ValueError("workspace item ids must be unique")
        if positions != tuple(range(len(positions))):
            raise ValueError("workspace item positions must be contiguous from zero")
        return self


class WorkflowFinding(FrozenModel):
    finding_id: Identifier
    code: WorkflowFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2005_MAX_EVIDENCE)


class PresentProteinSubtypeHumanReviewWorkspaceRequest(FrozenModel):
    """Provisional request for a protein-subtype human-review workspace."""

    operation: Literal["present_protein_subtype_human_review_workspace"] = M2005_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2005_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    aligned_evidence_bundle: ArtifactReference
    policy: PresentationPolicy
    review_items: tuple[ReviewItem, ...] = Field(min_length=1, max_length=M2005_MAX_ITEMS)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2005_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound_and_bounded(self) -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
        if self.aligned_evidence_bundle.media_type != M2005_M2004_RESULT_MEDIA_TYPE:
            raise ValueError("workspace request must bind the provisional M20-04 result")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        if len(self.review_items) > self.policy.maximum_items:
            raise ValueError("request exceeds configured workspace item limit")
        item_ids = tuple(item.item_id for item in self.review_items)
        positions = tuple(item.position for item in self.review_items)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("request review item ids must be unique")
        if positions != tuple(range(len(positions))):
            raise ValueError("request review item positions must be contiguous from zero")
        if {item.view_kind for item in self.review_items} != set(self.policy.required_views):
            raise ValueError("request must include every policy-required workspace view")
        artifact_keys = tuple((item.artifact_id, item.digest) for item in self.source_artifacts)
        if len(artifact_keys) != len(set(artifact_keys)):
            raise ValueError("source artifacts must be unique by id and digest")
        if (
            self.aligned_evidence_bundle.artifact_id,
            self.aligned_evidence_bundle.digest,
        ) not in set(artifact_keys):
            raise ValueError("source artifacts must include the aligned evidence bundle")
        return self


class ProteinSubtypeHumanReviewWorkspaceResult(FrozenModel):
    """Human-review workspace object with safe ordering and abstention."""

    output_type: Literal["protein_subtype_human_review_workspace"] = (
        "protein_subtype_human_review_workspace"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2005_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PresentProteinSubtypeHumanReviewWorkspaceRequest
    status: WorkspaceStatus
    workspace: HumanReviewWorkspace | None = None
    findings: tuple[WorkflowFinding, ...] = Field(default=(), max_length=M2005_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2005_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2005_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeHumanReviewWorkspaceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is WorkspaceStatus.PRESENTED:
            if (
                self.workspace is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("presented result requires a supported workspace")
            if not self.evidence:
                raise ValueError("presented result requires output evidence")
            if self.workspace.ordering is not self.request.policy.default_ordering:
                raise ValueError("workspace ordering must match the requested policy")
            workspace_ids = tuple(item.item_id for item in self.workspace.items)
            request_ids = tuple(item.item_id for item in self.request.review_items)
            if workspace_ids != request_ids:
                raise ValueError("workspace must preserve request review items in order")
            if (
                self.workspace.source_bundle.artifact_id
                != self.request.aligned_evidence_bundle.artifact_id
                or self.workspace.source_bundle.digest
                != self.request.aligned_evidence_bundle.digest
            ):
                raise ValueError("workspace source bundle must bind the aligned evidence bundle")
        elif (
            self.workspace is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no workspace and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("workflow finding ids must be unique")
        return self


__all__ = [
    "M2005_CONTRACT_VERSION",
    "M2005_DOSSIER_SHA256",
    "M2005_DOSSIER_SLICE",
    "M2005_GATE",
    "M2005_M2004_RESULT_MEDIA_TYPE",
    "M2005_MAX_ACTIONS",
    "M2005_MAX_CANONICAL_REQUEST_BYTES",
    "M2005_MAX_CANONICAL_RESULT_BYTES",
    "M2005_MAX_DISCREPANCIES",
    "M2005_MAX_EVIDENCE",
    "M2005_MAX_FINDINGS",
    "M2005_MAX_ITEMS",
    "M2005_MODULE_ID",
    "M2005_OPERATION",
    "M2005_OUTPUT_MEDIA_TYPE",
    "M2005_OWNER",
    "M2005_PARENT",
    "M2005_PROVISIONAL_ABI",
    "M2005_SAFETY_CLASS",
    "HumanReviewWorkspace",
    "NextAction",
    "OrderingPolicy",
    "PresentProteinSubtypeHumanReviewWorkspaceRequest",
    "PresentationConfiguration",
    "PresentationPolicy",
    "ProteinSubtypeHumanReviewWorkspaceResult",
    "ReviewItem",
    "ReviewItemStatus",
    "ViewKind",
    "WorkflowFinding",
    "WorkflowFindingCode",
    "WorkspaceStatus",
]
