"""Provisional M19-05 workflow presentation service contracts.

The M19-05 dossier requires task-specific views, evidence summaries,
uncertainty, discrepancies, provenance, and safe default ordering.  The ABI
is provisional; this service presents a human-review workspace and never
turns unsupported evidence into a negative finding.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m19_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 6692-6732.
M1905_MODULE_ID: Final = "GLIO-PROTEOGEN-M19-05"
M1905_OPERATION: Final = "present_proteotype_human_review_workspace"
M1905_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1905_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-05+json"
M1905_M1904_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-04+json"
M1905_PARENT: Final = "proteotype"
M1905_OWNER: Final = "Data engineering"
M1905_SAFETY_CLASS: Final = "S2"
M1905_GATE: Final = "G4"
M1905_PROVISIONAL_ABI: Final = True
M1905_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M1905_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN-M19-05:6692-6732"
M1905_MAX_ITEMS: Final = 256
M1905_MAX_EVIDENCE: Final = 64
M1905_MAX_DISCREPANCIES: Final = 128
M1905_MAX_ACTIONS: Final = 64
M1905_MAX_FINDINGS: Final = 64
M1905_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1905_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1905_EVIDENCE_CLAIM: Final = (
    "Caller-declared M19-05 workspace presentation evidence; issuer authority, biological "
    "truth and human-review decisions remain outside this service."
)


def _unique(values: Iterable[object], label: str) -> None:
    """Reject duplicate identifiers or digests instead of silently collapsing them."""

    material = tuple(values)
    if len(material) != len(set(material)):
        raise ValueError(f"{label} must be unique")


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1905_MAX_EVIDENCE)


class PresentationPolicy(FrozenModel):
    required_views: tuple[ViewKind, ...] = Field(min_length=1, max_length=8)
    default_ordering: OrderingPolicy = OrderingPolicy.SAFE_DEFAULT
    maximum_items: int = Field(ge=1, le=M1905_MAX_ITEMS)
    uncertainty_required: Literal[True] = True
    discrepancy_review_required: Literal[True] = True
    provenance_required: Literal[True] = True
    configuration: PresentationConfiguration

    @model_validator(mode="after")
    def required_views_are_unique(self) -> PresentationPolicy:
        _unique(self.required_views, "required workspace views")
        if set(self.required_views) != set(ViewKind):
            raise ValueError("presentation policy must require all six workspace views")
        return self


class NextAction(FrozenModel):
    action_id: Identifier
    label: NonEmptyStr
    rationale: NonEmptyStr
    required_evidence: tuple[ArtifactReference, ...] = Field(
        default=(), max_length=M1905_MAX_EVIDENCE
    )
    review_only: Literal[True] = True

    @model_validator(mode="after")
    def evidence_is_unique(self) -> NextAction:
        _unique(
            (artifact.digest for artifact in self.required_evidence),
            "next-action evidence",
        )
        return self


class ReviewItem(FrozenModel):
    item_id: Identifier
    view_kind: ViewKind
    title: NonEmptyStr
    position: int = Field(ge=0, le=M1905_MAX_ITEMS)
    status: ReviewItemStatus
    evidence_summary: NonEmptyStr
    uncertainty_summary: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1905_MAX_EVIDENCE)
    discrepancy_ids: tuple[Identifier, ...] = Field(default=(), max_length=M1905_MAX_DISCREPANCIES)
    provenance_artifact: ArtifactReference
    next_action: NextAction | None = None

    @model_validator(mode="after")
    def references_are_unique(self) -> ReviewItem:
        _unique(self.discrepancy_ids, "review item discrepancy ids")
        _unique((item.reference.digest for item in self.evidence), "review item evidence")
        return self


class HumanReviewWorkspace(FrozenModel):
    workspace_id: Identifier
    version: SemanticVersion
    parent_target: Literal["proteotype"] = M1905_PARENT
    items: tuple[ReviewItem, ...] = Field(min_length=1, max_length=M1905_MAX_ITEMS)
    ordering: OrderingPolicy
    safe_default_order: Literal[True] = True
    automation_bias_warning: NonEmptyStr
    source_bundle: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1905_MAX_EVIDENCE)

    @model_validator(mode="after")
    def items_are_unique_and_ordered(self) -> HumanReviewWorkspace:
        ids = tuple(item.item_id for item in self.items)
        positions = tuple(item.position for item in self.items)
        _unique(ids, "workspace item ids")
        if positions != tuple(range(len(positions))):
            raise ValueError("workspace item positions must be contiguous and strictly ordered")
        kinds = tuple(item.view_kind for item in self.items)
        _unique(kinds, "workspace view kinds")
        if set(kinds) != set(ViewKind):
            raise ValueError("workspace must contain exactly one item for every workspace view")
        _unique((item.provenance_artifact.digest for item in self.items), "workspace provenance")
        _unique((item.reference.digest for item in self.evidence), "workspace evidence")
        return self


class WorkflowFinding(FrozenModel):
    finding_id: Identifier
    code: WorkflowFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1905_MAX_EVIDENCE)


class PresentProteotypeHumanReviewWorkspaceRequest(FrozenModel):
    """Provisional request for a proteotype human-review workspace."""

    operation: Literal["present_proteotype_human_review_workspace"] = M1905_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1905_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    aligned_evidence_bundle: ArtifactReference
    policy: PresentationPolicy
    review_items: tuple[ReviewItem, ...] = Field(min_length=1, max_length=M1905_MAX_ITEMS)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1905_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound_and_bounded(self) -> PresentProteotypeHumanReviewWorkspaceRequest:
        if self.aligned_evidence_bundle.media_type != M1905_M1904_RESULT_MEDIA_TYPE:
            raise ValueError("workspace request must bind the provisional M19-04 result")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must match request id")
        if len(self.review_items) > self.policy.maximum_items:
            raise ValueError("request exceeds configured workspace item limit")
        _unique(
            (artifact.artifact_id for artifact in self.source_artifacts),
            "request source artifact ids",
        )
        _unique(
            (artifact.digest for artifact in self.source_artifacts),
            "request source artifact digests",
        )
        if self.aligned_evidence_bundle.artifact_id not in {
            artifact.artifact_id for artifact in self.source_artifacts
        }:
            raise ValueError("request source artifacts must include the bound M19-04 result")
        _unique((item.item_id for item in self.review_items), "request review item ids")
        positions = tuple(item.position for item in self.review_items)
        if positions != tuple(range(len(positions))):
            raise ValueError("request review item positions must be contiguous and ordered")
        if {item.view_kind for item in self.review_items} != set(self.policy.required_views):
            raise ValueError("request review items must cover every required workspace view")
        known_ids = {artifact.artifact_id for artifact in self.source_artifacts}
        known_digests = {artifact.digest for artifact in self.source_artifacts}
        for item in self.review_items:
            if item.provenance_artifact.artifact_id not in known_ids:
                raise ValueError("review item provenance references an unknown source artifact")
            if item.provenance_artifact.digest not in known_digests:
                raise ValueError("review item provenance digest is not a source artifact")
            if any(evidence.reference.artifact_id not in known_ids for evidence in item.evidence):
                raise ValueError("review item evidence references an unknown source artifact")
            if any(evidence.reference.digest not in known_digests for evidence in item.evidence):
                raise ValueError("review item evidence digest is not a source artifact")
        return self


class ProteotypeHumanReviewWorkspaceResult(FrozenModel):
    """Human-review workspace object with safe ordering and abstention."""

    output_type: Literal["proteotype_human_review_workspace"] = "proteotype_human_review_workspace"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1905_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PresentProteotypeHumanReviewWorkspaceRequest
    status: WorkspaceStatus
    workspace: HumanReviewWorkspace | None = None
    findings: tuple[WorkflowFinding, ...] = Field(default=(), max_length=M1905_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1905_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1905_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeHumanReviewWorkspaceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if self.provenance.module_id != M1905_MODULE_ID:
            raise ValueError("result provenance must identify M19-05")
        _unique((item.finding_id for item in self.findings), "result finding ids")
        _unique((item.reference.digest for item in self.evidence), "result evidence")
        if self.status is WorkspaceStatus.PRESENTED:
            if (
                self.workspace is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("presented result requires a supported workspace")
            if self.workspace.items != self.request.review_items:
                raise ValueError("presented workspace must bind exact request review items")
            if self.workspace.source_bundle != self.request.aligned_evidence_bundle:
                raise ValueError("presented workspace must bind the exact aligned evidence bundle")
        elif (
            self.workspace is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no workspace and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1905_CONTRACT_VERSION",
    "M1905_DOSSIER_SHA256",
    "M1905_DOSSIER_SLICE",
    "M1905_EVIDENCE_CLAIM",
    "M1905_GATE",
    "M1905_M1904_RESULT_MEDIA_TYPE",
    "M1905_MAX_ACTIONS",
    "M1905_MAX_CANONICAL_REQUEST_BYTES",
    "M1905_MAX_CANONICAL_RESULT_BYTES",
    "M1905_MAX_DISCREPANCIES",
    "M1905_MAX_EVIDENCE",
    "M1905_MAX_FINDINGS",
    "M1905_MAX_ITEMS",
    "M1905_MODULE_ID",
    "M1905_OPERATION",
    "M1905_OUTPUT_MEDIA_TYPE",
    "M1905_OWNER",
    "M1905_PARENT",
    "M1905_PROVISIONAL_ABI",
    "M1905_SAFETY_CLASS",
    "HumanReviewWorkspace",
    "NextAction",
    "OrderingPolicy",
    "PresentProteotypeHumanReviewWorkspaceRequest",
    "PresentationConfiguration",
    "PresentationPolicy",
    "ProteotypeHumanReviewWorkspaceResult",
    "ReviewItem",
    "ReviewItemStatus",
    "ViewKind",
    "WorkflowFinding",
    "WorkflowFindingCode",
    "WorkspaceStatus",
]
