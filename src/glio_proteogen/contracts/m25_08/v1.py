"""Provisional M25-08 evidence gate and release adjudicator contracts.

M25-08 owns traceability, risk controls, benchmark outcomes, claim ceilings,
residual risk, approvals and post-release obligations beneath Uncertainty/
stability/abstention. The ABI is provisional pending Platform engineering
owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m25_08.canonical import (
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

# PROVISIONAL ABI: inferred solely from dossier lines 8984-9024.
M2508_MODULE_ID: Final = "GLIO-PROTEOGEN-M25-08"
M2508_OPERATION: Final = "adjudicate_proteotype_evidence_gate"
M2508_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2508_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m25-08+json"
M2508_PARENT: Final = "proteotype"
M2508_OWNER: Final = "Platform engineering"
M2508_SAFETY_CLASS: Final = "S3"
M2508_GATE: Final = "G5"
M2508_PROVISIONAL_ABI: Final = True
M2508_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2508_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:8984-9024"
# M25-06 remains a declared media boundary; it is not imported as a runtime ABI.
M2508_M2506_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m25-06+json"
M2508_M2507_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m25-07+json"
M2508_MAX_REQUIREMENTS: Final = 128
M2508_MAX_BENCHMARKS: Final = 128
M2508_MAX_RISKS: Final = 128
M2508_MAX_APPROVALS: Final = 32
M2508_MAX_OBLIGATIONS: Final = 64
M2508_MAX_EVIDENCE: Final = 64
M2508_MAX_FINDINGS: Final = 64
M2508_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2508_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2508_EVIDENCE_CLAIM: Final = (
    "Caller-declared M25-08 traceability, risk-control, benchmark, approval "
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2508_MAX_EVIDENCE)


class BenchmarkOutcome(FrozenModel):
    benchmark_id: Identifier
    name: NonEmptyStr
    metric_name: NonEmptyStr
    observed_value: float = Field(allow_inf_nan=False)
    required_floor: float = Field(allow_inf_nan=False)
    passed: bool
    report_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2508_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2508_MAX_EVIDENCE)


class ApprovalRecord(FrozenModel):
    approval_id: Identifier
    approver_token: Identifier
    role: NonEmptyStr
    decision: ApprovalDecision
    signature_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2508_MAX_EVIDENCE)


class PostReleaseObligation(FrozenModel):
    obligation_id: Identifier
    owner: NonEmptyStr
    trigger: NonEmptyStr
    action: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2508_MAX_EVIDENCE)


class GateConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    parent_target: Literal["proteotype"] = M2508_PARENT
    require_traceability: Literal[True] = True
    require_risk_controls: Literal[True] = True
    require_benchmark_pass: Literal[True] = True
    require_claim_ceiling: Literal[True] = True
    require_no_open_critical_risk: Literal[True] = True
    require_signed_release_record: Literal[True] = True
    require_post_release_obligations: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2508_MAX_EVIDENCE)


class SignedReleaseRecord(FrozenModel):
    """Signed gate decision with limitations and post-release obligations."""

    release_id: Identifier
    version: SemanticVersion
    decision: GateDecision
    requirements: tuple[GateRequirement, ...] = Field(
        min_length=1, max_length=M2508_MAX_REQUIREMENTS
    )
    benchmarks: tuple[BenchmarkOutcome, ...] = Field(min_length=1, max_length=M2508_MAX_BENCHMARKS)
    residual_risks: tuple[ResidualRisk, ...] = Field(min_length=1, max_length=M2508_MAX_RISKS)
    approvals: tuple[ApprovalRecord, ...] = Field(min_length=1, max_length=M2508_MAX_APPROVALS)
    post_release_obligations: tuple[PostReleaseObligation, ...] = Field(
        min_length=1, max_length=M2508_MAX_OBLIGATIONS
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    signature_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2508_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2508_MAX_EVIDENCE)


class AdjudicateProteotypeEvidenceGateRequest(FrozenModel):
    """Provisional request for evidence gate and release adjudication."""

    operation: Literal["adjudicate_proteotype_evidence_gate"] = M2508_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2508_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    upstream_evidence: ArtifactReference
    requirements: tuple[GateRequirement, ...] = Field(
        min_length=1, max_length=M2508_MAX_REQUIREMENTS
    )
    benchmarks: tuple[BenchmarkOutcome, ...] = Field(min_length=1, max_length=M2508_MAX_BENCHMARKS)
    residual_risks: tuple[ResidualRisk, ...] = Field(min_length=1, max_length=M2508_MAX_RISKS)
    approvals: tuple[ApprovalRecord, ...] = Field(min_length=1, max_length=M2508_MAX_APPROVALS)
    post_release_obligations: tuple[PostReleaseObligation, ...] = Field(
        min_length=1, max_length=M2508_MAX_OBLIGATIONS
    )
    configuration: GateConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2508_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdjudicateProteotypeEvidenceGateRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        if self.upstream_evidence.media_type != M2508_M2507_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M25-07 evidence result")
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("request source artifacts must be unique")
        source_set = set(source_keys)
        required = (
            self.mass_spectrometry_proteome,
            self.genome_transcriptome,
            self.ptm_annotations,
            self.upstream_evidence,
        )
        if any(
            (item.artifact_id, item.version, item.digest, item.media_type) not in source_set
            for item in required
        ):
            raise ValueError("source artifacts must include every declared evidence artifact")
        if not any(
            item.media_type == M2508_M2506_INPUT_MEDIA_TYPE for item in self.source_artifacts
        ):
            raise ValueError("source artifacts must retain the M25-06 media-only evidence boundary")
        return self


class ProteotypeEvidenceGateResult(FrozenModel):
    """Gate decision, limitations and signed release record with abstention."""

    output_type: Literal["proteotype_evidence_gate"] = "proteotype_evidence_gate"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2508_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateProteotypeEvidenceGateRequest
    status: GateRunStatus
    release_record: SignedReleaseRecord | None = None
    findings: tuple[GateFinding, ...] = Field(default=(), max_length=M2508_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M2508_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2508_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeEvidenceGateResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request):
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
            expected_release_id = "release." + self.request_digest.removeprefix("sha256:")
            expected_signature = sha256_digest(f"M2508.release:{self.request_digest}")
            if (
                self.release_record.release_id != expected_release_id
                or self.release_record.version != self.request.configuration.version
                or self.release_record.requirements != self.request.requirements
                or self.release_record.benchmarks != self.request.benchmarks
                or self.release_record.residual_risks != self.request.residual_risks
                or self.release_record.approvals != self.request.approvals
                or self.release_record.post_release_obligations
                != self.request.post_release_obligations
                or self.release_record.signature_digest != expected_signature
            ):
                raise ValueError("adjudicated release record must bind exact request declarations")
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
    "M2508_CONTRACT_VERSION",
    "M2508_DOSSIER_SHA256",
    "M2508_DOSSIER_SLICE",
    "M2508_EVIDENCE_CLAIM",
    "M2508_GATE",
    "M2508_M2506_INPUT_MEDIA_TYPE",
    "M2508_M2507_INPUT_MEDIA_TYPE",
    "M2508_MAX_APPROVALS",
    "M2508_MAX_BENCHMARKS",
    "M2508_MAX_CANONICAL_REQUEST_BYTES",
    "M2508_MAX_CANONICAL_RESULT_BYTES",
    "M2508_MAX_EVIDENCE",
    "M2508_MAX_FINDINGS",
    "M2508_MAX_OBLIGATIONS",
    "M2508_MAX_REQUIREMENTS",
    "M2508_MAX_RISKS",
    "M2508_MODULE_ID",
    "M2508_OPERATION",
    "M2508_OUTPUT_MEDIA_TYPE",
    "M2508_OWNER",
    "M2508_PARENT",
    "M2508_PROVISIONAL_ABI",
    "M2508_SAFETY_CLASS",
    "AdjudicateProteotypeEvidenceGateRequest",
    "ApprovalDecision",
    "ApprovalRecord",
    "BenchmarkOutcome",
    "GateConfiguration",
    "GateDecision",
    "GateFinding",
    "GateFindingCode",
    "GateRequirement",
    "GateRunStatus",
    "PostReleaseObligation",
    "ProteotypeEvidenceGateResult",
    "RequirementCategory",
    "ResidualRisk",
    "RiskSeverity",
    "SignedReleaseRecord",
]
