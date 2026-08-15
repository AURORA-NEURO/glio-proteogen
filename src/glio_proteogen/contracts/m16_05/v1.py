"""Provisional M16-05 workflow presentation service contracts.

The M16-05 dossier requires task-specific views, evidence summaries,
uncertainty, discrepancies, provenance, and safe default ordering. The
workspace is review support only: it must not silently resolve conflicts or
make a treatment decision. All symbols are provisional pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m16_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M16-05 dossier slice.
M1605_MODULE_ID: Final = "GLIO-PROTEOGEN-M16-05"
M1605_OPERATION: Final = "present_protein_rna_review_workspace"
M1605_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1605_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-05+json"
M1605_M1604_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-04+json"
M1605_PARENT: Final = "protein_rna_discordance"
M1605_OWNER: Final = "ML engineering"
M1605_SAFETY_CLASS: Final = "S2"
M1605_GATE: Final = "G4"
M1605_PROVISIONAL_ABI: Final = True
M1605_MAX_VIEWS: Final = 16
M1605_MAX_ITEMS_PER_VIEW: Final = 256
M1605_MAX_ITEM_SOURCES: Final = 64
M1605_MAX_EVIDENCE: Final = 64
M1605_MAX_DIAGNOSTICS: Final = 128
M1605_MAX_FINDINGS: Final = 64
M1605_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1605_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1605_EVIDENCE_CLAIM: Final = (
    "Caller-declared M16-05 workflow presentation and review material; issuer "
    "authority is not authenticated."
)


class WorkspaceViewKind(StrEnum):
    TASK = "task"
    EVIDENCE = "evidence"
    UNCERTAINTY = "uncertainty"
    DISCREPANCY = "discrepancy"
    PROVENANCE = "provenance"
    NEXT_ACTION = "next_action"


class WorkspaceItemStatus(StrEnum):
    AVAILABLE = "available"
    WARNING = "warning"
    BLOCKED = "blocked"
    NOT_EVALUABLE = "not_evaluable"


class WorkspacePresentationStatus(StrEnum):
    PRESENTED = "presented"
    REVIEW_REQUIRED = "review_required"
    ABSTAINED = "abstained"


class WorkspaceDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class WorkspaceFindingCode(StrEnum):
    MISSING_TASK_VIEW = "missing_task_view"
    SAFE_ORDERING_INVALID = "safe_ordering_invalid"
    DISCREPANCY_NOT_VISIBLE = "discrepancy_not_visible"
    PROVENANCE_NOT_VISIBLE = "provenance_not_visible"
    AUTOMATION_BIAS_CONTROL_MISSING = "automation_bias_control_missing"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class WorkspaceItem(FrozenModel):
    item_id: Identifier
    title: NonEmptyStr
    summary: NonEmptyStr
    kind: WorkspaceViewKind
    status: WorkspaceItemStatus
    priority: int = Field(ge=1, le=M1605_MAX_ITEMS_PER_VIEW)
    next_action: NonEmptyStr | None = None
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1605_MAX_ITEM_SOURCES
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1605_MAX_EVIDENCE)


class WorkspaceView(FrozenModel):
    view_id: Identifier
    kind: WorkspaceViewKind
    title: NonEmptyStr
    purpose: NonEmptyStr
    items: tuple[WorkspaceItem, ...] = Field(
        min_length=1, max_length=M1605_MAX_ITEMS_PER_VIEW
    )
    default_item_order: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M1605_MAX_ITEMS_PER_VIEW
    )
    safe_default: Literal[True] = True

    @model_validator(mode="after")
    def ordering_is_closed(self) -> WorkspaceView:
        item_ids = tuple(item.item_id for item in self.items)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("workspace item ids must be unique within a view")
        if set(self.default_item_order) != set(item_ids) or len(self.default_item_order) != len(
            set(self.default_item_order)
        ):
            raise ValueError("default item order must contain every item exactly once")
        return self


class WorkspaceConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    default_view_order: tuple[WorkspaceViewKind, ...] = Field(
        min_length=1, max_length=M1605_MAX_VIEWS
    )
    visible_sections: tuple[WorkspaceViewKind, ...] = Field(
        min_length=1, max_length=M1605_MAX_VIEWS
    )
    automation_decision_disabled: Literal[True] = True
    conflict_preservation_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def view_order_is_unique(self) -> WorkspaceConfiguration:
        if len(self.default_view_order) != len(set(self.default_view_order)):
            raise ValueError("default view order must be unique")
        return self


class HumanReviewWorkspace(FrozenModel):
    """Versioned review workspace with explicit safe defaults."""

    workspace_id: Identifier
    version: SemanticVersion
    views: tuple[WorkspaceView, ...] = Field(min_length=1, max_length=M1605_MAX_VIEWS)
    configuration: WorkspaceConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def workspace_is_closed(self) -> HumanReviewWorkspace:
        view_ids = tuple(view.view_id for view in self.views)
        if len(view_ids) != len(set(view_ids)):
            raise ValueError("workspace view ids must be unique")
        kinds = {view.kind for view in self.views}
        if not set(self.configuration.default_view_order) <= kinds:
            raise ValueError("default view order references a missing view")
        if not set(self.configuration.visible_sections) <= kinds:
            raise ValueError("visible sections reference a missing view")
        return self


class WorkspaceDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: WorkspaceDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1605_MAX_EVIDENCE)


class PresentProteinRnaReviewWorkspaceRequest(FrozenModel):
    """Provisional request bound to the M16-04 upstream integration object."""

    operation: Literal["present_protein_rna_review_workspace"] = M1605_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1605_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: WorkspaceConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1605_MAX_ITEM_SOURCES
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> PresentProteinRnaReviewWorkspaceRequest:
        if self.upstream_result.media_type != M1605_M1604_INPUT_MEDIA_TYPE:
            raise ValueError("workspace request must bind the provisional M16-04 result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("workspace source artifact references must be unique")
        return self


class ProteinRnaDiscordanceReviewWorkspaceResult(FrozenModel):
    """Human-review workspace with safe defaults and explicit abstention."""

    output_type: Literal["protein_rna_discordance_review_workspace"] = (
        "protein_rna_discordance_review_workspace"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1605_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PresentProteinRnaReviewWorkspaceRequest
    status: WorkspacePresentationStatus
    workspace: HumanReviewWorkspace | None = None
    diagnostics: tuple[WorkspaceDiagnostic, ...] = Field(
        min_length=1, max_length=M1605_MAX_DIAGNOSTICS
    )
    findings: tuple[WorkspaceFindingCode, ...] = Field(default=(), max_length=M1605_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1605_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1605_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceReviewWorkspaceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        blocked = bool(
            self.workspace
            and any(
                item.status in {WorkspaceItemStatus.BLOCKED, WorkspaceItemStatus.NOT_EVALUABLE}
                for view in self.workspace.views
                for item in view.items
            )
        )
        if self.status is WorkspacePresentationStatus.PRESENTED:
            if (
                self.workspace is None
                or blocked
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("presented workspace requires supported, unblocked content")
        elif self.status is WorkspacePresentationStatus.REVIEW_REQUIRED:
            if (
                self.workspace is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
            ):
                raise ValueError("review workspace requires explicit human review")
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
    "M1605_CONTRACT_VERSION",
    "M1605_EVIDENCE_CLAIM",
    "M1605_GATE",
    "M1605_M1604_INPUT_MEDIA_TYPE",
    "M1605_MAX_CANONICAL_REQUEST_BYTES",
    "M1605_MAX_CANONICAL_RESULT_BYTES",
    "M1605_MAX_DIAGNOSTICS",
    "M1605_MAX_EVIDENCE",
    "M1605_MAX_FINDINGS",
    "M1605_MAX_ITEMS_PER_VIEW",
    "M1605_MAX_ITEM_SOURCES",
    "M1605_MAX_VIEWS",
    "M1605_MODULE_ID",
    "M1605_OPERATION",
    "M1605_OUTPUT_MEDIA_TYPE",
    "M1605_OWNER",
    "M1605_PARENT",
    "M1605_PROVISIONAL_ABI",
    "M1605_SAFETY_CLASS",
    "HumanReviewWorkspace",
    "PresentProteinRnaReviewWorkspaceRequest",
    "ProteinRnaDiscordanceReviewWorkspaceResult",
    "WorkspaceConfiguration",
    "WorkspaceDiagnostic",
    "WorkspaceDiagnosticStatus",
    "WorkspaceFindingCode",
    "WorkspaceItem",
    "WorkspaceItemStatus",
    "WorkspacePresentationStatus",
    "WorkspaceView",
    "WorkspaceViewKind",
]
