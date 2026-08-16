"""Provisional M18-05 workflow presentation service contracts.

M18-05 owns a human-review workspace with task-specific views, evidence,
uncertainty, discrepancies, provenance and safe default ordering beneath
Spatial proteomics projection.  The public ABI is provisional pending Clinical
science owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m18_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M18-05 dossier slice.
M1805_MODULE_ID: Final = "GLIO-PROTEOGEN-M18-05"
M1805_OPERATION: Final = "present_biomarker_panel_review_workspace"
M1805_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1805_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-05+json"
M1805_M1804_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-04+json"
M1805_PARENT: Final = "biomarker panel"
M1805_OWNER: Final = "Clinical science"
M1805_SAFETY_CLASS: Final = "S2"
M1805_GATE: Final = "G4"
M1805_PROVISIONAL_ABI: Final = True
M1805_MAX_SECTIONS: Final = 32
M1805_MAX_NEXT_ACTIONS: Final = 32
M1805_MAX_EVIDENCE: Final = 64
M1805_MAX_FINDINGS: Final = 64
M1805_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1805_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1805_EVIDENCE_CLAIM: Final = (
    "Caller-declared M18-05 workspace, evidence, uncertainty, discrepancy and "
    "provenance presentation material; issuer authority is not authenticated."
)


class WorkspaceSectionKind(StrEnum):
    TASK_SUMMARY = "task_summary"
    EVIDENCE_SUMMARY = "evidence_summary"
    UNCERTAINTY = "uncertainty"
    DISCREPANCIES = "discrepancies"
    PROVENANCE = "provenance"
    NEXT_ACTION = "next_action"


class WorkspaceStatus(StrEnum):
    PRESENTED = "presented"
    ABSTAINED = "abstained"


class WorkspaceFindingCode(StrEnum):
    REQUIRED_VIEW_MISSING = "required_view_missing"
    UNSAFE_ORDERING = "unsafe_ordering"
    AUTOMATION_BIAS_RISK = "automation_bias_risk"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class WorkspaceSection(FrozenModel):
    section_id: Identifier
    kind: WorkspaceSectionKind
    title: NonEmptyStr
    summary: NonEmptyStr
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1805_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1805_MAX_EVIDENCE)


class WorkspaceConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_sections: tuple[WorkspaceSectionKind, ...] = Field(min_length=6, max_length=6)
    safe_default_section: WorkspaceSectionKind = WorkspaceSectionKind.TASK_SUMMARY
    automation_bias_warning: NonEmptyStr
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1805_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_views_are_required(self) -> WorkspaceConfiguration:
        if set(self.required_sections) != set(WorkspaceSectionKind):
            raise ValueError("workspace configuration must require all six view sections")
        return self


class HumanReviewWorkspace(FrozenModel):
    """Human-review workspace with safe ordering and complete presentation views."""

    workspace_id: Identifier
    version: SemanticVersion
    sections: tuple[WorkspaceSection, ...] = Field(min_length=6, max_length=M1805_MAX_SECTIONS)
    default_section_order: tuple[Identifier, ...] = Field(
        min_length=6, max_length=M1805_MAX_SECTIONS
    )
    next_actions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1805_MAX_NEXT_ACTIONS)
    configuration: WorkspaceConfiguration
    human_review_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1805_MAX_EVIDENCE)

    @model_validator(mode="after")
    def workspace_is_closed(self) -> HumanReviewWorkspace:
        section_ids = tuple(item.section_id for item in self.sections)
        kinds = tuple(item.kind for item in self.sections)
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("workspace section ids must be unique")
        if set(kinds) != set(self.configuration.required_sections):
            raise ValueError("workspace must include every required section kind")
        if set(self.default_section_order) != set(section_ids):
            raise ValueError("default section order must include every section exactly once")
        if self.default_section_order[0] not in section_ids:
            raise ValueError("default section order must begin with a known section")
        return self


class WorkspaceFinding(FrozenModel):
    finding_id: Identifier
    code: WorkspaceFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1805_MAX_EVIDENCE)


class PresentBiomarkerPanelReviewWorkspaceRequest(FrozenModel):
    """Provisional request bound to the M18-04 intended-use object."""

    operation: Literal["present_biomarker_panel_review_workspace"] = M1805_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1805_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    sections: tuple[WorkspaceSection, ...] = Field(min_length=6, max_length=M1805_MAX_SECTIONS)
    default_section_order: tuple[Identifier, ...] = Field(
        min_length=6, max_length=M1805_MAX_SECTIONS
    )
    next_actions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1805_MAX_NEXT_ACTIONS)
    configuration: WorkspaceConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1805_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> PresentBiomarkerPanelReviewWorkspaceRequest:
        if self.upstream_result.media_type != M1805_M1804_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M18-04 intended-use result")
        section_ids = tuple(item.section_id for item in self.sections)
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("request workspace section ids must be unique")
        if set(self.default_section_order) != set(section_ids):
            raise ValueError("request default order must cover every section")
        return self


class BiomarkerPanelReviewWorkspaceResult(FrozenModel):
    """Human-review workspace with explicit support and safe abstention."""

    output_type: Literal["biomarker_panel_review_workspace"] = "biomarker_panel_review_workspace"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1805_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PresentBiomarkerPanelReviewWorkspaceRequest
    status: WorkspaceStatus
    workspace: HumanReviewWorkspace | None = None
    findings: tuple[WorkspaceFinding, ...] = Field(default=(), max_length=M1805_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M1805_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1805_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelReviewWorkspaceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is WorkspaceStatus.PRESENTED:
            if (
                self.workspace is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("presented result requires a supported review workspace")
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
    "M1805_CONTRACT_VERSION",
    "M1805_EVIDENCE_CLAIM",
    "M1805_GATE",
    "M1805_M1804_INPUT_MEDIA_TYPE",
    "M1805_MAX_CANONICAL_REQUEST_BYTES",
    "M1805_MAX_CANONICAL_RESULT_BYTES",
    "M1805_MAX_EVIDENCE",
    "M1805_MAX_FINDINGS",
    "M1805_MAX_NEXT_ACTIONS",
    "M1805_MAX_SECTIONS",
    "M1805_MODULE_ID",
    "M1805_OPERATION",
    "M1805_OUTPUT_MEDIA_TYPE",
    "M1805_OWNER",
    "M1805_PARENT",
    "M1805_PROVISIONAL_ABI",
    "M1805_SAFETY_CLASS",
    "BiomarkerPanelReviewWorkspaceResult",
    "HumanReviewWorkspace",
    "PresentBiomarkerPanelReviewWorkspaceRequest",
    "WorkspaceConfiguration",
    "WorkspaceFinding",
    "WorkspaceFindingCode",
    "WorkspaceSection",
    "WorkspaceSectionKind",
    "WorkspaceStatus",
]
