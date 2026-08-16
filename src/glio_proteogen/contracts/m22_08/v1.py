"""Provisional M22-08 evidence gate and release adjudicator contracts.

M22-08 owns traceability, risk controls, benchmark outcomes, claim ceilings,
residual risk, approvals and post-release obligations beneath Orthogonal
immunoassay validation.  The ABI is provisional pending Quality engineering
owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m22_08.canonical import (
    canonical_request_digest,
    result_identifier,
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

# PROVISIONAL ABI: inferred solely from dossier lines 7904-7944.
M2208_MODULE_ID: Final = "GLIO-PROTEOGEN-M22-08"
M2208_OPERATION: Final = "adjudicate_protein_rna_discordance_evidence_gate"
M2208_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2208_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-08+json"
M2208_PARENT: Final = "protein-RNA discordance"
M2208_OWNER: Final = "Quality engineering"
M2208_SAFETY_CLASS: Final = "S3"
M2208_GATE: Final = "G5"
M2208_PROVISIONAL_ABI: Final = True
M2208_MAX_REQUIREMENTS: Final = 128
M2208_MAX_BENCHMARKS: Final = 128
M2208_MAX_RISKS: Final = 128
M2208_MAX_APPROVALS: Final = 32
M2208_MAX_OBLIGATIONS: Final = 64
M2208_MAX_EVIDENCE: Final = 64
M2208_MAX_FINDINGS: Final = 64
M2208_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2208_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2208_EVIDENCE_CLAIM: Final = (
    "Caller-declared M22-08 traceability, risk-control, benchmark, approval "
    "and release material; issuer authority is not authenticated."
)
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2208_MAX_EVIDENCE)


class BenchmarkOutcome(FrozenModel):
    benchmark_id: Identifier
    name: NonEmptyStr
    metric_name: NonEmptyStr
    observed_value: FiniteFloat
    required_floor: FiniteFloat
    passed: bool
    report_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2208_MAX_EVIDENCE)

    @model_validator(mode="after")
    def pass_matches_floor(self) -> BenchmarkOutcome:
        expected = self.observed_value >= self.required_floor
        if self.passed != expected:
            raise ValueError("benchmark passed flag must match its required floor")
        return self


class ResidualRisk(FrozenModel):
    risk_id: Identifier
    severity: RiskSeverity
    statement: NonEmptyStr
    mitigation: NonEmptyStr
    accepted: bool
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2208_MAX_EVIDENCE)


class ApprovalRecord(FrozenModel):
    approval_id: Identifier
    approver_token: Identifier
    role: NonEmptyStr
    decision: ApprovalDecision
    signature_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2208_MAX_EVIDENCE)


class PostReleaseObligation(FrozenModel):
    obligation_id: Identifier
    owner: NonEmptyStr
    trigger: NonEmptyStr
    action: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2208_MAX_EVIDENCE)


class GateConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    parent_target: Literal["protein-RNA discordance"] = M2208_PARENT
    require_traceability: Literal[True] = True
    require_risk_controls: Literal[True] = True
    require_benchmark_pass: Literal[True] = True
    require_claim_ceiling: Literal[True] = True
    require_no_open_critical_risk: Literal[True] = True
    require_signed_release_record: Literal[True] = True
    require_post_release_obligations: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2208_MAX_EVIDENCE)


class SignedReleaseRecord(FrozenModel):
    """Signed gate decision with limitations and post-release obligations."""

    release_id: Identifier
    version: SemanticVersion
    decision: GateDecision
    requirements: tuple[GateRequirement, ...] = Field(
        min_length=1, max_length=M2208_MAX_REQUIREMENTS
    )
    benchmarks: tuple[BenchmarkOutcome, ...] = Field(min_length=1, max_length=M2208_MAX_BENCHMARKS)
    residual_risks: tuple[ResidualRisk, ...] = Field(min_length=1, max_length=M2208_MAX_RISKS)
    approvals: tuple[ApprovalRecord, ...] = Field(min_length=1, max_length=M2208_MAX_APPROVALS)
    post_release_obligations: tuple[PostReleaseObligation, ...] = Field(
        min_length=1, max_length=M2208_MAX_OBLIGATIONS
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    signature_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2208_MAX_EVIDENCE)

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
        categories = {item.category for item in self.requirements}
        if categories != set(RequirementCategory):
            raise ValueError("gate record must cover every required requirement category")
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2208_MAX_EVIDENCE)


class AdjudicateProteinRnaDiscordanceEvidenceGateRequest(FrozenModel):
    """Provisional request for evidence gate and release adjudication."""

    operation: Literal["adjudicate_protein_rna_discordance_evidence_gate"] = M2208_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2208_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    upstream_evidence: ArtifactReference
    requirements: tuple[GateRequirement, ...] = Field(
        min_length=1, max_length=M2208_MAX_REQUIREMENTS
    )
    benchmarks: tuple[BenchmarkOutcome, ...] = Field(min_length=1, max_length=M2208_MAX_BENCHMARKS)
    residual_risks: tuple[ResidualRisk, ...] = Field(min_length=1, max_length=M2208_MAX_RISKS)
    approvals: tuple[ApprovalRecord, ...] = Field(min_length=1, max_length=M2208_MAX_APPROVALS)
    post_release_obligations: tuple[PostReleaseObligation, ...] = Field(
        min_length=1, max_length=M2208_MAX_OBLIGATIONS
    )
    configuration: GateConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2208_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> AdjudicateProteinRnaDiscordanceEvidenceGateRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request ID must match the request")
        collections = (
            (item.requirement_id for item in self.requirements),
            (item.benchmark_id for item in self.benchmarks),
            (item.risk_id for item in self.residual_risks),
            (item.approval_id for item in self.approvals),
            (item.obligation_id for item in self.post_release_obligations),
        )
        if any(len(values := tuple(group)) != len(set(values)) for group in collections):
            raise ValueError("request record identifiers must be unique")
        if {item.category for item in self.requirements} != set(RequirementCategory):
            raise ValueError("request must cover every required requirement category")
        required = (
            self.mass_spectrometry_proteome,
            self.genome_transcriptome,
            self.ptm_annotations,
            self.upstream_evidence,
        )
        source_by_id = {item.artifact_id: item for item in self.source_artifacts}
        if len(source_by_id) != len(self.source_artifacts):
            raise ValueError("source artifacts must have unique artifact IDs")
        if any(source_by_id.get(item.artifact_id) != item for item in required):
            raise ValueError("source artifacts must bind every declared input exactly")
        return self


class ProteinRnaDiscordanceEvidenceGateResult(FrozenModel):
    """Gate decision, limitations and signed release record with abstention."""

    output_type: Literal["protein_rna_discordance_evidence_gate"] = (
        "protein_rna_discordance_evidence_gate"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2208_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest
    status: GateRunStatus
    release_record: SignedReleaseRecord | None = None
    findings: tuple[GateFinding, ...] = Field(default=(), max_length=M2208_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein-RNA discordance"] = M2208_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2208_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceEvidenceGateResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is GateRunStatus.ADJUDICATED:
            _validate_adjudicated_result(self)
        else:
            _validate_abstained_result(self)
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def _validate_adjudicated_result(result: ProteinRnaDiscordanceEvidenceGateResult) -> None:
    if (
        result.release_record is None
        or result.abstention_reason is not None
        or result.support_decision.status is not SupportStatus.SUPPORTED
    ):
        raise ValueError("adjudicated result requires a supported release record")
    if result.findings and not all(item.evidence for item in result.findings):
        raise ValueError("adjudicated findings must carry evidence")
    if result.result_id != result_identifier(result.request_digest):
        raise ValueError("result identifier must bind the request digest")
    record = result.release_record
    request = result.request
    if record.requirements != request.requirements:
        raise ValueError("release requirements must bind the request")
    if record.benchmarks != request.benchmarks:
        raise ValueError("release benchmarks must bind the request")
    if record.residual_risks != request.residual_risks:
        raise ValueError("release risks must bind the request")
    if record.approvals != request.approvals:
        raise ValueError("release approvals must bind the request")
    if record.post_release_obligations != request.post_release_obligations:
        raise ValueError("release obligations must bind the request")


def _validate_abstained_result(result: ProteinRnaDiscordanceEvidenceGateResult) -> None:
    if (
        result.release_record is not None
        or result.abstention_reason is None
        or result.support_decision.status
        not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
    ):
        raise ValueError("abstained result requires no release record and safe status")
    if not result.findings:
        raise ValueError("abstained result must retain at least one finding")
    if result.result_id != result_identifier(result.request_digest):
        raise ValueError("result identifier must bind the request digest")


__all__ = [
    "M2208_CONTRACT_VERSION",
    "M2208_EVIDENCE_CLAIM",
    "M2208_GATE",
    "M2208_MAX_APPROVALS",
    "M2208_MAX_BENCHMARKS",
    "M2208_MAX_CANONICAL_REQUEST_BYTES",
    "M2208_MAX_CANONICAL_RESULT_BYTES",
    "M2208_MAX_EVIDENCE",
    "M2208_MAX_FINDINGS",
    "M2208_MAX_OBLIGATIONS",
    "M2208_MAX_REQUIREMENTS",
    "M2208_MAX_RISKS",
    "M2208_MODULE_ID",
    "M2208_OPERATION",
    "M2208_OUTPUT_MEDIA_TYPE",
    "M2208_OWNER",
    "M2208_PARENT",
    "M2208_PROVISIONAL_ABI",
    "M2208_SAFETY_CLASS",
    "AdjudicateProteinRnaDiscordanceEvidenceGateRequest",
    "ApprovalDecision",
    "ApprovalRecord",
    "BenchmarkOutcome",
    "FiniteFloat",
    "GateConfiguration",
    "GateDecision",
    "GateFinding",
    "GateFindingCode",
    "GateRequirement",
    "GateRunStatus",
    "PostReleaseObligation",
    "ProteinRnaDiscordanceEvidenceGateResult",
    "RequirementCategory",
    "ResidualRisk",
    "RiskSeverity",
    "SignedReleaseRecord",
]
