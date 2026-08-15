"""Provisional M24-08 evidence gate and release adjudicator contracts.

M24-08 owns traceability, risk controls, benchmark outcomes, claim ceilings,
residual risk, approvals and post-release obligations beneath Batch/missing-
protein sensitivity. The ABI is provisional pending Data engineering owner
confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m24_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 8624-8664.
M2408_MODULE_ID: Final = "GLIO-PROTEOGEN-M24-08"
M2408_OPERATION: Final = "adjudicate_biomarker_panel_evidence_gate"
M2408_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2408_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m24-08+json"
M2408_PARENT: Final = "biomarker panel"
M2408_OWNER: Final = "Data engineering"
M2408_SAFETY_CLASS: Final = "S3"
M2408_GATE: Final = "G5"
M2408_PROVISIONAL_ABI: Final = True
M2408_MAX_REQUIREMENTS: Final = 128
M2408_MAX_BENCHMARKS: Final = 128
M2408_MAX_RISKS: Final = 128
M2408_MAX_APPROVALS: Final = 32
M2408_MAX_OBLIGATIONS: Final = 64
M2408_MAX_EVIDENCE: Final = 64
M2408_MAX_FINDINGS: Final = 64
M2408_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2408_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2408_EVIDENCE_CLAIM: Final = (
    "Caller-declared M24-08 traceability, risk-control, benchmark, approval "
    "and release material; issuer authority is not authenticated."
)


class GateDecision(StrEnum):
    PASS = "pass"  # noqa: S105
    BLOCK = "block"
    REVIEW_REQUIRED = "review_required"


class GateRunStatus(StrEnum):
    ADJUDICATED = "adjudicated"
    ABSTAINED = "abstained"


class RequirementCategory(StrEnum):
    TRACEABILITY = "traceability"
    RISK_CONTROL = "risk_control"
    BENCHMARK = "benchmark"
    CLAIM_CEILING = "claim_ceiling"
    APPROVAL = "approval"
    POST_RELEASE = "post_release"


class RiskSeverity(StrEnum):
    CRITICAL = "critical"
    MATERIAL = "material"
    ROUTINE = "routine"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"


class GateFindingCode(StrEnum):
    REQUIREMENT_UNSATISFIED = "requirement_unsatisfied"
    BENCHMARK_FAILED = "benchmark_failed"
    CRITICAL_RISK_OPEN = "critical_risk_open"
    APPROVAL_MISSING = "approval_missing"
    SIGNATURE_MISSING = "signature_missing"
    POST_RELEASE_OBLIGATION_MISSING = "post_release_obligation_missing"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class GateRequirement(FrozenModel):
    requirement_id: Identifier
    category: RequirementCategory
    statement: NonEmptyStr
    satisfied: bool
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2408_MAX_EVIDENCE)


class BenchmarkOutcome(FrozenModel):
    benchmark_id: Identifier
    name: NonEmptyStr
    metric_name: NonEmptyStr
    observed_value: float
    required_floor: float
    passed: bool
    report_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2408_MAX_EVIDENCE)

    @model_validator(mode="after")
    def pass_matches_floor(self) -> BenchmarkOutcome:
        if self.passed and self.observed_value < self.required_floor:
            raise ValueError("passed benchmark must meet its required floor")
        return self


class ResidualRisk(FrozenModel):
    risk_id: Identifier
    severity: RiskSeverity
    statement: NonEmptyStr
    mitigation: NonEmptyStr
    accepted: bool
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2408_MAX_EVIDENCE)


class ApprovalRecord(FrozenModel):
    approval_id: Identifier
    approver_token: Identifier
    role: NonEmptyStr
    decision: ApprovalDecision
    signature_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2408_MAX_EVIDENCE)


class PostReleaseObligation(FrozenModel):
    obligation_id: Identifier
    owner: NonEmptyStr
    trigger: NonEmptyStr
    action: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2408_MAX_EVIDENCE)


class GateConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    parent_target: Literal["biomarker panel"] = M2408_PARENT
    require_traceability: Literal[True] = True
    require_risk_controls: Literal[True] = True
    require_benchmark_pass: Literal[True] = True
    require_claim_ceiling: Literal[True] = True
    require_no_open_critical_risk: Literal[True] = True
    require_signed_release_record: Literal[True] = True
    require_post_release_obligations: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2408_MAX_EVIDENCE)


class SignedReleaseRecord(FrozenModel):
    """Signed gate decision with limitations and post-release obligations."""

    release_id: Identifier
    version: SemanticVersion
    decision: GateDecision
    requirements: tuple[GateRequirement, ...] = Field(
        min_length=1, max_length=M2408_MAX_REQUIREMENTS
    )
    benchmarks: tuple[BenchmarkOutcome, ...] = Field(
        min_length=1, max_length=M2408_MAX_BENCHMARKS
    )
    residual_risks: tuple[ResidualRisk, ...] = Field(min_length=1, max_length=M2408_MAX_RISKS)
    approvals: tuple[ApprovalRecord, ...] = Field(min_length=1, max_length=M2408_MAX_APPROVALS)
    post_release_obligations: tuple[PostReleaseObligation, ...] = Field(
        min_length=1, max_length=M2408_MAX_OBLIGATIONS
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    signature_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2408_MAX_EVIDENCE)

    @model_validator(mode="after")
    def record_is_closed(self) -> SignedReleaseRecord:
        requirement_ids = tuple(item.requirement_id for item in self.requirements)
        benchmark_ids = tuple(item.benchmark_id for item in self.benchmarks)
        risk_ids = tuple(item.risk_id for item in self.residual_risks)
        approval_ids = tuple(item.approval_id for item in self.approvals)
        obligation_ids = tuple(item.obligation_id for item in self.post_release_obligations)
        groups = (requirement_ids, benchmark_ids, risk_ids, approval_ids, obligation_ids)
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("gate record identifiers must be unique")
        if self.decision is GateDecision.PASS:
            if any(not item.satisfied for item in self.requirements):
                raise ValueError("passing gate cannot contain unsatisfied requirements")
            if any(not item.passed for item in self.benchmarks):
                raise ValueError("passing gate cannot contain failed benchmarks")
            if any(
                item.severity is RiskSeverity.CRITICAL and not item.accepted
                for item in self.residual_risks
            ):
                raise ValueError("passing gate cannot contain open critical risk")
            if any(item.decision is not ApprovalDecision.APPROVE for item in self.approvals):
                raise ValueError("passing gate requires approval records")
        return self


class GateFinding(FrozenModel):
    finding_id: Identifier
    code: GateFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2408_MAX_EVIDENCE)


class AdjudicateBiomarkerPanelEvidenceGateRequest(FrozenModel):
    """Provisional request for evidence gate and release adjudication."""

    operation: Literal["adjudicate_biomarker_panel_evidence_gate"] = M2408_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2408_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    upstream_evidence: ArtifactReference
    requirements: tuple[GateRequirement, ...] = Field(
        min_length=1, max_length=M2408_MAX_REQUIREMENTS
    )
    benchmarks: tuple[BenchmarkOutcome, ...] = Field(
        min_length=1, max_length=M2408_MAX_BENCHMARKS
    )
    residual_risks: tuple[ResidualRisk, ...] = Field(min_length=1, max_length=M2408_MAX_RISKS)
    approvals: tuple[ApprovalRecord, ...] = Field(min_length=1, max_length=M2408_MAX_APPROVALS)
    post_release_obligations: tuple[PostReleaseObligation, ...] = Field(
        min_length=1, max_length=M2408_MAX_OBLIGATIONS
    )
    configuration: GateConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2408_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None


class BiomarkerPanelEvidenceGateResult(FrozenModel):
    """Gate decision, limitations and signed release record with abstention."""

    output_type: Literal["biomarker_panel_evidence_gate"] = "biomarker_panel_evidence_gate"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2408_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateBiomarkerPanelEvidenceGateRequest
    status: GateRunStatus
    release_record: SignedReleaseRecord | None = None
    findings: tuple[GateFinding, ...] = Field(default=(), max_length=M2408_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M2408_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2408_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelEvidenceGateResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is GateRunStatus.ADJUDICATED:
            if (
                self.release_record is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("adjudicated result requires a supported release record")
        elif (
            self.release_record is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no release record and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2408_CONTRACT_VERSION",
    "M2408_EVIDENCE_CLAIM",
    "M2408_GATE",
    "M2408_MAX_APPROVALS",
    "M2408_MAX_BENCHMARKS",
    "M2408_MAX_CANONICAL_REQUEST_BYTES",
    "M2408_MAX_CANONICAL_RESULT_BYTES",
    "M2408_MAX_EVIDENCE",
    "M2408_MAX_FINDINGS",
    "M2408_MAX_OBLIGATIONS",
    "M2408_MAX_REQUIREMENTS",
    "M2408_MAX_RISKS",
    "M2408_MODULE_ID",
    "M2408_OPERATION",
    "M2408_OUTPUT_MEDIA_TYPE",
    "M2408_OWNER",
    "M2408_PARENT",
    "M2408_PROVISIONAL_ABI",
    "M2408_SAFETY_CLASS",
    "AdjudicateBiomarkerPanelEvidenceGateRequest",
    "ApprovalDecision",
    "ApprovalRecord",
    "BenchmarkOutcome",
    "BiomarkerPanelEvidenceGateResult",
    "GateConfiguration",
    "GateDecision",
    "GateFinding",
    "GateFindingCode",
    "GateRequirement",
    "GateRunStatus",
    "PostReleaseObligation",
    "RequirementCategory",
    "ResidualRisk",
    "RiskSeverity",
    "SignedReleaseRecord",
]
