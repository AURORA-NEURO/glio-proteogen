"""Provisional M21-08 evidence gate and release adjudicator contracts.

M21-08 owns traceability, risk controls, benchmark outcomes, claim ceilings,
residual risk, approvals and post-release obligations for complex-activity
release. The ABI is provisional pending ML engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, FiniteFloat, model_validator

from glio_proteogen.contracts.m21_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M21-08 dossier slice.
M2108_MODULE_ID: Final = "GLIO-PROTEOGEN-M21-08"
M2108_OPERATION: Final = "adjudicate_complex_activity_evidence_gate"
M2108_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2108_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-08+json"
M2108_M2107_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-07+json"
M2108_M2106_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-06+json"
M2108_PARENT: Final = "complex activity"
M2108_OWNER: Final = "ML engineering"
M2108_SAFETY_CLASS: Final = "S3"
M2108_GATE: Final = "G5"
M2108_PROVISIONAL_ABI: Final = True
M2108_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2108_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7544-7584"
M2108_MAX_REQUIREMENTS: Final = 128
M2108_MAX_BENCHMARKS: Final = 128
M2108_MAX_RISKS: Final = 128
M2108_MAX_APPROVALS: Final = 32
M2108_MAX_OBLIGATIONS: Final = 64
M2108_MAX_EVIDENCE: Final = 64
M2108_MAX_FINDINGS: Final = 64
M2108_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2108_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2108_EVIDENCE_CLAIM: Final = (
    "Caller-declared M21-08 traceability, risk-control, benchmark, approval "
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2108_MAX_EVIDENCE)


class BenchmarkOutcome(FrozenModel):
    benchmark_id: Identifier
    name: NonEmptyStr
    metric_name: NonEmptyStr
    observed_value: FiniteFloat
    required_floor: FiniteFloat
    passed: bool
    report_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2108_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2108_MAX_EVIDENCE)


class ApprovalRecord(FrozenModel):
    approval_id: Identifier
    approver_token: Identifier
    role: NonEmptyStr
    decision: ApprovalDecision
    signature_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2108_MAX_EVIDENCE)


class PostReleaseObligation(FrozenModel):
    obligation_id: Identifier
    owner: NonEmptyStr
    trigger: NonEmptyStr
    action: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2108_MAX_EVIDENCE)


class GateConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    parent_target: Literal["complex activity"] = M2108_PARENT
    require_benchmark_pass: Literal[True] = True
    require_no_open_critical_risk: Literal[True] = True
    require_signed_release_record: Literal[True] = True
    require_post_release_obligations: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2108_MAX_EVIDENCE)


class SignedReleaseRecord(FrozenModel):
    """Signed gate decision with limitations and post-release obligations."""

    release_id: Identifier
    version: SemanticVersion
    decision: GateDecision
    requirements: tuple[GateRequirement, ...] = Field(
        min_length=1, max_length=M2108_MAX_REQUIREMENTS
    )
    benchmarks: tuple[BenchmarkOutcome, ...] = Field(min_length=1, max_length=M2108_MAX_BENCHMARKS)
    residual_risks: tuple[ResidualRisk, ...] = Field(min_length=1, max_length=M2108_MAX_RISKS)
    approvals: tuple[ApprovalRecord, ...] = Field(min_length=1, max_length=M2108_MAX_APPROVALS)
    post_release_obligations: tuple[PostReleaseObligation, ...] = Field(
        min_length=1, max_length=M2108_MAX_OBLIGATIONS
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    signature_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2108_MAX_EVIDENCE)

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
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("gate record evidence must be unique")
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2108_MAX_EVIDENCE)


class AdjudicateComplexActivityEvidenceGateRequest(FrozenModel):
    """Provisional request for evidence gate and release adjudication."""

    operation: Literal["adjudicate_complex_activity_evidence_gate"] = M2108_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2108_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_evidence: ArtifactReference
    requirements: tuple[GateRequirement, ...] = Field(
        min_length=1, max_length=M2108_MAX_REQUIREMENTS
    )
    benchmarks: tuple[BenchmarkOutcome, ...] = Field(min_length=1, max_length=M2108_MAX_BENCHMARKS)
    residual_risks: tuple[ResidualRisk, ...] = Field(min_length=1, max_length=M2108_MAX_RISKS)
    approvals: tuple[ApprovalRecord, ...] = Field(min_length=1, max_length=M2108_MAX_APPROVALS)
    post_release_obligations: tuple[PostReleaseObligation, ...] = Field(
        min_length=1, max_length=M2108_MAX_OBLIGATIONS
    )
    configuration: GateConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2108_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdjudicateComplexActivityEvidenceGateRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        if self.upstream_evidence.media_type != M2108_M2107_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M21-07 operational result")
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("request source artifacts must be unique")
        if (
            self.upstream_evidence.artifact_id,
            self.upstream_evidence.version,
            self.upstream_evidence.digest,
            self.upstream_evidence.media_type,
        ) not in set(source_keys):
            raise ValueError("request source artifacts must include M21-07 evidence")
        m2106_sources = tuple(
            item
            for item in self.source_artifacts
            if item.media_type == M2108_M2106_INPUT_MEDIA_TYPE
        )
        if len(m2106_sources) != 1:
            raise ValueError(
                "request source artifacts must retain exactly one M21-06 robustness evidence"
            )
        return self


class ComplexActivityEvidenceGateResult(FrozenModel):
    """Gate decision, limitations and signed release record with abstention."""

    output_type: Literal["complex_activity_evidence_gate"] = "complex_activity_evidence_gate"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2108_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateComplexActivityEvidenceGateRequest
    status: GateRunStatus
    release_record: SignedReleaseRecord | None = None
    findings: tuple[GateFinding, ...] = Field(default=(), max_length=M2108_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2108_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2108_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityEvidenceGateResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("gate finding ids must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("gate result evidence must be unique")
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
    "M2108_CONTRACT_VERSION",
    "M2108_DOSSIER_SHA256",
    "M2108_DOSSIER_SLICE",
    "M2108_EVIDENCE_CLAIM",
    "M2108_GATE",
    "M2108_M2106_INPUT_MEDIA_TYPE",
    "M2108_M2107_INPUT_MEDIA_TYPE",
    "M2108_MAX_APPROVALS",
    "M2108_MAX_BENCHMARKS",
    "M2108_MAX_CANONICAL_REQUEST_BYTES",
    "M2108_MAX_CANONICAL_RESULT_BYTES",
    "M2108_MAX_EVIDENCE",
    "M2108_MAX_FINDINGS",
    "M2108_MAX_OBLIGATIONS",
    "M2108_MAX_REQUIREMENTS",
    "M2108_MAX_RISKS",
    "M2108_MODULE_ID",
    "M2108_OPERATION",
    "M2108_OUTPUT_MEDIA_TYPE",
    "M2108_OWNER",
    "M2108_PARENT",
    "M2108_PROVISIONAL_ABI",
    "M2108_SAFETY_CLASS",
    "AdjudicateComplexActivityEvidenceGateRequest",
    "ApprovalDecision",
    "ApprovalRecord",
    "BenchmarkOutcome",
    "ComplexActivityEvidenceGateResult",
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
