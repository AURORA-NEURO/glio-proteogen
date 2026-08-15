"""Provisional M17-05 workflow presentation service contracts.

The dossier requires a human-review workspace containing task-specific views,
evidence summaries, uncertainty, discrepancies, provenance, and safe default
ordering.  The ABI is not frozen; this contract never makes the downstream
decision itself and preserves safe abstention for the variant-peptide parent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m17_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 5972-6015.
M1705_MODULE_ID: Final = "GLIO-PROTEOGEN-M17-05"
M1705_OPERATION: Final = "present_variant_peptide_human_review_workspace"
M1705_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1705_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m17-05+json"
M1705_M1702_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m17-02+json"
M1705_PARENT: Final = "variant_peptide"
M1705_OWNER: Final = "Quality engineering"
M1705_SAFETY_CLASS: Final = "S2"
M1705_GATE: Final = "G4"
M1705_PROVISIONAL_ABI: Final = True
M1705_MAX_ITEMS: Final = 256
M1705_MAX_EVIDENCE: Final = 64
M1705_MAX_DISCREPANCIES: Final = 128
M1705_MAX_ACTIONS: Final = 64
M1705_MAX_FINDINGS: Final = 64
M1705_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1705_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


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


class PresentationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    automation_bias_guard_required: Literal[True] = True
    safe_default_order_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1705_MAX_EVIDENCE)


class PresentationPolicy(FrozenModel):
    required_views: tuple[ViewKind, ...] = Field(min_length=1, max_length=8)
    default_ordering: OrderingPolicy = OrderingPolicy.SAFE_DEFAULT
    maximum_items: int = Field(ge=1, le=M1705_MAX_ITEMS)
    uncertainty_required: Literal[True] = True
    discrepancy_review_required: Literal[True] = True
    provenance_required: Literal[True] = True
    configuration: PresentationConfiguration

    @model_validator(mode="after")
    def required_views_are_unique(self) -> PresentationPolicy:
        if len(set(self.required_views)) != len(self.required_views):
            raise ValueError("required workspace views must be unique")
        return self


class NextAction(FrozenModel):
    action_id: Identifier
    label: NonEmptyStr
    rationale: NonEmptyStr
    required_evidence: tuple[ArtifactReference, ...] = Field(
        default=(), max_length=M1705_MAX_EVIDENCE
    )
    review_only: Literal[True] = True


class ReviewItem(FrozenModel):
    item_id: Identifier
    view_kind: ViewKind
    title: NonEmptyStr
    position: int = Field(ge=0, le=M1705_MAX_ITEMS)
    status: ReviewItemStatus
    evidence_summary: NonEmptyStr
    uncertainty_summary: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1705_MAX_EVIDENCE)
    discrepancy_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1705_MAX_DISCREPANCIES
    )
    provenance_artifact: ArtifactReference
    next_action: NextAction | None = None


class HumanReviewWorkspace(FrozenModel):
    workspace_id: Identifier
    version: SemanticVersion
    parent_target: Literal["variant_peptide"] = M1705_PARENT
    items: tuple[ReviewItem, ...] = Field(min_length=1, max_length=M1705_MAX_ITEMS)
    ordering: OrderingPolicy
    safe_default_order: Literal[True] = True
    automation_bias_warning: NonEmptyStr
    source_bundle: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1705_MAX_EVIDENCE)

    @model_validator(mode="after")
    def items_are_unique_and_ordered(self) -> HumanReviewWorkspace:
        ids = tuple(item.item_id for item in self.items)
        positions = tuple(item.position for item in self.items)
        if len(ids) != len(set(ids)):
            raise ValueError("workspace item ids must be unique")
        if positions != tuple(range(len(positions))):
            raise ValueError("workspace item positions must be contiguous and zero-based")
        return self


class WorkflowFinding(FrozenModel):
    finding_id: Identifier
    code: WorkflowFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1705_MAX_EVIDENCE)


class PresentVariantPeptideHumanReviewWorkspaceRequest(FrozenModel):
    """Provisional request for a human-review workspace."""

    operation: Literal["present_variant_peptide_human_review_workspace"] = M1705_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1705_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    aligned_evidence_bundle: ArtifactReference
    policy: PresentationPolicy
    review_items: tuple[ReviewItem, ...] = Field(min_length=1, max_length=M1705_MAX_ITEMS)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1705_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound_and_bounded(self) -> PresentVariantPeptideHumanReviewWorkspaceRequest:
        if self.aligned_evidence_bundle.media_type != M1705_M1702_RESULT_MEDIA_TYPE:
            raise ValueError("workspace request must bind the provisional M17-02 result")
        if len(self.review_items) > self.policy.maximum_items:
            raise ValueError("request exceeds configured workspace item limit")
        item_ids = tuple(item.item_id for item in self.review_items)
        positions = tuple(item.position for item in self.review_items)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("request review item ids must be unique")
        if positions != tuple(range(len(positions))):
            raise ValueError("request review item positions must be contiguous and zero-based")
        required = set(self.policy.required_views)
        present = {item.view_kind for item in self.review_items}
        if not required.issubset(present):
            raise ValueError("request must provide every policy-required workspace view")
        source_digests = tuple(artifact.digest for artifact in self.source_artifacts)
        if len(source_digests) != len(set(source_digests)):
            raise ValueError("request source artifacts must be unique")
        if self.aligned_evidence_bundle.digest not in source_digests:
            raise ValueError("aligned evidence bundle must be listed in source artifacts")
        for item in self.review_items:
            if item.provenance_artifact.digest not in source_digests:
                raise ValueError("review item provenance must bind a request source artifact")
            if any(evidence.reference.digest not in source_digests for evidence in item.evidence):
                raise ValueError("review item evidence must bind request source artifacts")
        return self


class VariantPeptideHumanReviewWorkspaceResult(FrozenModel):
    """Human-review workspace object with safe ordering and abstention."""

    output_type: Literal["variant_peptide_human_review_workspace"] = (
        "variant_peptide_human_review_workspace"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1705_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PresentVariantPeptideHumanReviewWorkspaceRequest
    status: WorkspaceStatus
    workspace: HumanReviewWorkspace | None = None
    findings: tuple[WorkflowFinding, ...] = Field(default=(), max_length=M1705_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant_peptide"] = M1705_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1705_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideHumanReviewWorkspaceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is WorkspaceStatus.PRESENTED:
            if (
                self.workspace is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("presented result requires a supported workspace")
            if self.workspace.ordering is not self.request.policy.default_ordering:
                raise ValueError("workspace ordering must bind the requested policy")
            if self.workspace.source_bundle.digest != self.request.aligned_evidence_bundle.digest:
                raise ValueError("workspace source bundle must bind the aligned evidence bundle")
            request_ids = tuple(item.item_id for item in self.request.review_items)
            workspace_ids = tuple(item.item_id for item in self.workspace.items)
            if workspace_ids != request_ids:
                raise ValueError("workspace items must bind the request item sequence")
        elif (
            self.workspace is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no workspace and safe status")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        finding_codes = tuple(finding.code for finding in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("result finding ids must be unique")
        if len(finding_codes) != len(set(finding_codes)):
            raise ValueError("result finding codes must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1705_CONTRACT_VERSION",
    "M1705_GATE",
    "M1705_M1702_RESULT_MEDIA_TYPE",
    "M1705_MAX_ACTIONS",
    "M1705_MAX_CANONICAL_REQUEST_BYTES",
    "M1705_MAX_CANONICAL_RESULT_BYTES",
    "M1705_MAX_DISCREPANCIES",
    "M1705_MAX_EVIDENCE",
    "M1705_MAX_FINDINGS",
    "M1705_MAX_ITEMS",
    "M1705_MODULE_ID",
    "M1705_OPERATION",
    "M1705_OUTPUT_MEDIA_TYPE",
    "M1705_OWNER",
    "M1705_PARENT",
    "M1705_PROVISIONAL_ABI",
    "M1705_SAFETY_CLASS",
    "HumanReviewWorkspace",
    "NextAction",
    "OrderingPolicy",
    "PresentVariantPeptideHumanReviewWorkspaceRequest",
    "PresentationConfiguration",
    "PresentationPolicy",
    "ReviewItem",
    "ReviewItemStatus",
    "VariantPeptideHumanReviewWorkspaceResult",
    "ViewKind",
    "WorkflowFinding",
    "WorkflowFindingCode",
    "WorkspaceStatus",
]
