"""Provisional M27-07 change-control and rollback contracts.

Every change requires classification, impact assessment, revalidation,
champion/challenger comparison, approval, staged rollout, and a tested
rollback point. Critical regressions block promotion; the ABI is provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m27_07.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier SHA
# 0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181,
# lines 9660-9700. Owner confirmation and implementation details remain
# pending.
M2707_MODULE_ID: Final = "GLIO-PROTEOGEN-M27-07"
M2707_OPERATION: Final = "control_complex_activity_change"
M2707_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2707_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-07+json"
M2707_M2706_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-06+json"
M2707_PARENT: Final = "complex activity"
M2707_OWNER: Final = "Scientific engineering"
M2707_SAFETY_CLASS: Final = "S3"
M2707_GATE: Final = "G5"
M2707_PROVISIONAL_ABI: Final = True
M2707_MAX_CHECKS: Final = 64
M2707_MAX_METRICS: Final = 64
M2707_MAX_EVIDENCE: Final = 64
M2707_MAX_FINDINGS: Final = 64
M2707_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2707_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class ChangeKind(StrEnum):
    DATA = "data"
    FEATURE = "feature"
    MODEL = "model"
    POLICY = "policy"
    REFERENCE = "reference"
    INFRASTRUCTURE = "infrastructure"


class ChangeRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PromotionState(StrEnum):
    PROPOSED = "proposed"
    SHADOW = "shadow"
    STAGED = "staged"
    APPROVED = "approved"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class ComparisonStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"


class ChangeControlStatus(StrEnum):
    APPROVED = "approved"
    ABSTAINED = "abstained"


class ChangeFindingCode(StrEnum):
    REVALIDATION_MISSING = "revalidation_missing"
    CHALLENGER_REGRESSION = "challenger_regression"
    APPROVAL_MISSING = "approval_missing"
    ROLLBACK_UNTESTED = "rollback_untested"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class ChangeClassification(FrozenModel):
    change_id: Identifier
    kind: ChangeKind
    risk: ChangeRisk
    summary: NonEmptyStr
    impact_scope: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M2707_MAX_CHECKS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2707_MAX_EVIDENCE)


class RevalidationPlan(FrozenModel):
    plan_id: Identifier
    version: SemanticVersion
    required_checks: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M2707_MAX_CHECKS)
    completed_checks: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M2707_MAX_CHECKS)
    validation_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def checks_are_complete(self) -> RevalidationPlan:
        if not set(self.required_checks).issubset(set(self.completed_checks)):
            raise ValueError("all required revalidation checks must be completed")
        return self


class MetricComparison(FrozenModel):
    metric: NonEmptyStr
    champion_value: float
    challenger_value: float
    tolerance: float = Field(ge=0.0)
    within_tolerance: bool
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2707_MAX_EVIDENCE)


class ChampionChallengerComparison(FrozenModel):
    comparison_id: Identifier
    champion_digest: Sha256Digest
    challenger_digest: Sha256Digest
    status: ComparisonStatus
    metrics: tuple[MetricComparison, ...] = Field(min_length=1, max_length=M2707_MAX_METRICS)
    shadow_complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def comparisons_are_distinct(self) -> ChampionChallengerComparison:
        if self.champion_digest == self.challenger_digest:
            raise ValueError("champion and challenger must be distinct")
        return self


class RollbackPoint(FrozenModel):
    rollback_id: Identifier
    version: SemanticVersion
    target_digest: Sha256Digest
    tested: Literal[True] = True
    rollback_reason: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2707_MAX_EVIDENCE)


class ApprovedChangePackage(FrozenModel):
    package_id: Identifier
    version: SemanticVersion
    classification: ChangeClassification
    revalidation: RevalidationPlan
    comparison: ChampionChallengerComparison
    approval_reference: NonEmptyStr
    promotion_state: PromotionState
    rollback_point: RollbackPoint
    package_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def promotion_is_authorized(self) -> ApprovedChangePackage:
        if (
            self.promotion_state is PromotionState.APPROVED
            and self.comparison.status is not ComparisonStatus.PASSED
        ):
            raise ValueError("only a passing comparison may be approved")
        if (
            self.promotion_state in {PromotionState.REJECTED, PromotionState.ROLLED_BACK}
            and not self.rollback_point.tested
        ):
            raise ValueError("rejected or rolled-back package requires tested rollback")
        return self


class ChangeFinding(FrozenModel):
    finding_id: Identifier
    code: ChangeFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2707_MAX_EVIDENCE)


class SafeFailureReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    trigger: NonEmptyStr
    action: NonEmptyStr
    abstained: Literal[True] = True
    recovery_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2707_MAX_EVIDENCE)


class ControlComplexActivityChangeRequest(FrozenModel):
    """Provisional request bound to the M27-06 security result."""

    operation: Literal["control_complex_activity_change"] = M2707_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2707_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    classification: ChangeClassification
    revalidation: RevalidationPlan
    champion_digest: Sha256Digest
    challenger_digest: Sha256Digest
    rollback_point: RollbackPoint
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2707_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ControlComplexActivityChangeRequest:
        if self.upstream_result.media_type != M2707_M2706_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M27-06 security result")
        if self.champion_digest == self.challenger_digest:
            raise ValueError("champion and challenger digests must be distinct")
        source_by_id = {item.artifact_id: item for item in self.source_artifacts}
        if len(source_by_id) != len(self.source_artifacts):
            raise ValueError("source artifact IDs must be unique")
        declared_artifacts = (
            self.upstream_result,
            *(item.reference for item in self.classification.evidence),
            *(item.reference for item in self.revalidation.evidence),
            *(item.reference for item in self.rollback_point.evidence),
        )
        if any(source_by_id.get(item.artifact_id) != item for item in declared_artifacts):
            raise ValueError(
                "source artifacts must bind upstream and change-control evidence exactly"
            )
        return self


class ComplexActivityChangeControlResult(FrozenModel):
    """Approved change package and rollback point or safe failure."""

    output_type: Literal["complex_activity_change_control"] = "complex_activity_change_control"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2707_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ControlComplexActivityChangeRequest
    status: ChangeControlStatus
    approved_change_package: ApprovedChangePackage | None = None
    findings: tuple[ChangeFinding, ...] = Field(default=(), max_length=M2707_MAX_FINDINGS)
    safe_failure_report: SafeFailureReport | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2707_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2707_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityChangeControlResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is ChangeControlStatus.APPROVED:
            if (
                self.approved_change_package is None
                or self.safe_failure_report is not None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("approved result requires a supported change package")
            if (
                self.approved_change_package.classification != self.request.classification
                or self.approved_change_package.revalidation != self.request.revalidation
                or self.approved_change_package.rollback_point != self.request.rollback_point
                or self.approved_change_package.comparison.champion_digest
                != self.request.champion_digest
                or self.approved_change_package.comparison.challenger_digest
                != self.request.challenger_digest
            ):
                raise ValueError("approved package must bind exact request change controls")
        elif (
            self.approved_change_package is not None
            or self.safe_failure_report is None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires safe failure and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2707_CONTRACT_VERSION",
    "M2707_GATE",
    "M2707_M2706_INPUT_MEDIA_TYPE",
    "M2707_MAX_CANONICAL_REQUEST_BYTES",
    "M2707_MAX_CANONICAL_RESULT_BYTES",
    "M2707_MAX_CHECKS",
    "M2707_MAX_EVIDENCE",
    "M2707_MAX_FINDINGS",
    "M2707_MAX_METRICS",
    "M2707_MODULE_ID",
    "M2707_OPERATION",
    "M2707_OUTPUT_MEDIA_TYPE",
    "M2707_OWNER",
    "M2707_PARENT",
    "M2707_PROVISIONAL_ABI",
    "M2707_SAFETY_CLASS",
    "ApprovedChangePackage",
    "ChampionChallengerComparison",
    "ChangeClassification",
    "ChangeControlStatus",
    "ChangeFinding",
    "ChangeFindingCode",
    "ChangeKind",
    "ChangeRisk",
    "ComparisonStatus",
    "ComplexActivityChangeControlResult",
    "ControlComplexActivityChangeRequest",
    "MetricComparison",
    "PromotionState",
    "RevalidationPlan",
    "RollbackPoint",
    "SafeFailureReport",
]
