"""Provisional M26-07 change-control, champion-challenger, and rollback contracts.

M26-07 owns change classification, revalidation, shadow comparison, staged
rollout, approval, and tested rollback beneath the Proteomics standards
registry. The ABI is inferred from dossier lines 9300-9340 and remains
provisional pending Platform engineering confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m26_07.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 9300-9340.
M2607_MODULE_ID: Final = "GLIO-PROTEOGEN-M26-07"
M2607_OPERATION: Final = "control_protein_subtype_change_and_rollback"
M2607_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2607_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-07+json"
M2607_PARENT: Final = "protein subtype"
M2607_OWNER: Final = "Platform engineering"
M2607_SAFETY_CLASS: Final = "S3"
M2607_GATE: Final = "G5"
M2607_PROVISIONAL_ABI: Final = True
M2607_MAX_REVALIDATIONS: Final = 128
M2607_MAX_COMPARISONS: Final = 128
M2607_MAX_EVIDENCE: Final = 64
M2607_MAX_FINDINGS: Final = 64
M2607_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2607_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2607_EVIDENCE_CLAIM: Final = (
    "Caller-declared M26-07 change classification, champion-challenger, staged "
    "rollout and rollback material; issuer authority is not authenticated."
)


class ChangeClass(StrEnum):
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"
    EMERGENCY = "emergency"


class ChangeImpact(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class RolloutStage(StrEnum):
    SHADOW = "shadow"
    CANARY = "canary"
    STAGED = "staged"
    FULL = "full"
    ROLLED_BACK = "rolled_back"


class ChangeStatus(StrEnum):
    APPROVED = "approved"
    ABSTAINED = "abstained"


class ChangeFindingCode(StrEnum):
    REVALIDATION_REQUIRED = "revalidation_required"
    CHAMPION_REGRESSION = "champion_regression"
    ROLLBACK_UNTESTED = "rollback_untested"
    APPROVAL_MISSING = "approval_missing"
    QUARANTINED_INPUT = "quarantined_input"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class ChangeProposal(FrozenModel):
    """Versioned change request with explicit impact and revalidation scope."""

    proposal_id: Identifier
    current_version: SemanticVersion
    proposed_version: SemanticVersion
    change_class: ChangeClass
    impact: ChangeImpact
    champion_digest: Sha256Digest
    challenger_digest: Sha256Digest
    rationale: NonEmptyStr
    required_revalidation_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M2607_MAX_REVALIDATIONS
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2607_MAX_EVIDENCE)


class RevalidationRecord(FrozenModel):
    """One completed pre-promotion validation gate."""

    revalidation_id: Identifier
    proposal_id: Identifier
    check_name: NonEmptyStr
    passed: bool
    report_digest: Sha256Digest
    completed_at: AwareDatetime
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2607_MAX_EVIDENCE)


class ShadowComparison(FrozenModel):
    """Champion/challenger comparison with an explicit regression decision."""

    comparison_id: Identifier
    proposal_id: Identifier
    metric_name: NonEmptyStr
    champion_value: float
    challenger_value: float
    tolerance: float = Field(ge=0.0)
    no_regression: bool
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2607_MAX_EVIDENCE)

    @model_validator(mode="after")
    def regression_decision_matches_values(self) -> ShadowComparison:
        if self.no_regression and self.challenger_value > self.champion_value + self.tolerance:
            raise ValueError("no-regression comparison exceeds declared tolerance")
        return self


class RollbackPoint(FrozenModel):
    """Immutable restore point whose recovery path has been tested."""

    rollback_id: Identifier
    target_version: SemanticVersion
    restore_artifact: ArtifactReference
    restore_command: NonEmptyStr
    tested: Literal[True] = True
    recovery_objective: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2607_MAX_EVIDENCE)


class ChangePackage(FrozenModel):
    """Approved package binding revalidation, comparison, rollout, and rollback."""

    package_id: Identifier
    version: SemanticVersion
    proposal: ChangeProposal
    revalidations: tuple[RevalidationRecord, ...] = Field(
        min_length=1, max_length=M2607_MAX_REVALIDATIONS
    )
    comparisons: tuple[ShadowComparison, ...] = Field(
        min_length=1, max_length=M2607_MAX_COMPARISONS
    )
    rollout_stage: RolloutStage
    approved_by: Identifier | None = None
    rollback_point: RollbackPoint
    package_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2607_MAX_EVIDENCE)

    @model_validator(mode="after")
    def promotion_is_gated(self) -> ChangePackage:
        required = set(self.proposal.required_revalidation_ids)
        actual = {item.revalidation_id for item in self.revalidations if item.passed}
        if not required <= actual:
            raise ValueError("change package lacks passing required revalidation")
        if any(item.proposal_id != self.proposal.proposal_id for item in self.revalidations):
            raise ValueError("revalidation belongs to a different proposal")
        if any(item.proposal_id != self.proposal.proposal_id for item in self.comparisons):
            raise ValueError("comparison belongs to a different proposal")
        if any(not item.no_regression for item in self.comparisons):
            raise ValueError("critical regression prevents change promotion")
        if (
            self.rollout_stage in {RolloutStage.CANARY, RolloutStage.STAGED, RolloutStage.FULL}
            and self.approved_by is None
        ):
            raise ValueError("promoted rollout requires an approver")
        return self


class ChangeFinding(FrozenModel):
    finding_id: Identifier
    code: ChangeFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2607_MAX_EVIDENCE)


class ControlProteinSubtypeChangeRequest(FrozenModel):
    """Provisional request for change control and tested rollback."""

    operation: Literal["control_protein_subtype_change_and_rollback"] = M2607_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2607_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    proposal: ChangeProposal
    revalidations: tuple[RevalidationRecord, ...] = Field(
        min_length=1, max_length=M2607_MAX_REVALIDATIONS
    )
    comparisons: tuple[ShadowComparison, ...] = Field(
        min_length=1, max_length=M2607_MAX_COMPARISONS
    )
    rollback_point: RollbackPoint
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2607_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_gated(self) -> ControlProteinSubtypeChangeRequest:
        required = set(self.proposal.required_revalidation_ids)
        actual = {item.revalidation_id for item in self.revalidations if item.passed}
        if not required <= actual:
            raise ValueError("request lacks passing required revalidation")
        if any(item.proposal_id != self.proposal.proposal_id for item in self.revalidations):
            raise ValueError("request revalidation belongs to a different proposal")
        if any(item.proposal_id != self.proposal.proposal_id for item in self.comparisons):
            raise ValueError("request comparison belongs to a different proposal")
        if any(not item.no_regression for item in self.comparisons):
            raise ValueError("critical regression prevents promotion")
        return self


class ProteinSubtypeChangeControlResult(FrozenModel):
    """Approved change package and rollback point with safe abstention."""

    output_type: Literal["protein_subtype_change_control"] = "protein_subtype_change_control"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2607_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ControlProteinSubtypeChangeRequest
    status: ChangeStatus
    change_package: ChangePackage | None = None
    rollback_point: RollbackPoint | None = None
    findings: tuple[ChangeFinding, ...] = Field(default=(), max_length=M2607_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2607_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2607_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeChangeControlResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.status is ChangeStatus.APPROVED:
            if (
                self.change_package is None
                or self.rollback_point is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("approved result requires supported package and rollback point")
        elif (
            self.change_package is not None
            or self.rollback_point is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no package and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2607_CONTRACT_VERSION",
    "M2607_EVIDENCE_CLAIM",
    "M2607_GATE",
    "M2607_MAX_CANONICAL_REQUEST_BYTES",
    "M2607_MAX_CANONICAL_RESULT_BYTES",
    "M2607_MAX_COMPARISONS",
    "M2607_MAX_EVIDENCE",
    "M2607_MAX_FINDINGS",
    "M2607_MAX_REVALIDATIONS",
    "M2607_MODULE_ID",
    "M2607_OPERATION",
    "M2607_OUTPUT_MEDIA_TYPE",
    "M2607_OWNER",
    "M2607_PARENT",
    "M2607_PROVISIONAL_ABI",
    "M2607_SAFETY_CLASS",
    "ChangeClass",
    "ChangeFinding",
    "ChangeFindingCode",
    "ChangeImpact",
    "ChangePackage",
    "ChangeProposal",
    "ChangeStatus",
    "ControlProteinSubtypeChangeRequest",
    "ProteinSubtypeChangeControlResult",
    "RevalidationRecord",
    "RollbackPoint",
    "RolloutStage",
    "ShadowComparison",
]
