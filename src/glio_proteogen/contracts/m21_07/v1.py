"""Provisional M21-07 human-factors and operational evaluator contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, FiniteFloat, model_validator

from glio_proteogen.contracts.m21_07.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 7500-7540.
M2107_MODULE_ID: Final = "GLIO-PROTEOGEN-M21-07"
M2107_OPERATION: Final = "evaluate_complex_activity_human_factors"
M2107_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2107_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-07+json"
M2107_M2106_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-06+json"
M2107_PARENT: Final = "complex activity"
M2107_OWNER: Final = "Bioinformatics"
M2107_SAFETY_CLASS: Final = "S3"
M2107_GATE: Final = "G4"
M2107_PROVISIONAL_ABI: Final = True
M2107_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2107_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7500-7540"
M2107_MAX_METRICS: Final = 256
M2107_MAX_FALLBACKS: Final = 64
M2107_MAX_EVIDENCE: Final = 64
M2107_MAX_FINDINGS: Final = 64
M2107_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2107_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2107_EVIDENCE_CLAIM: Final = (
    "Caller-declared M21-07 reviewer comprehension, automation-bias, throughput, "
    "latency, downtime, recovery and fallback material; issuer authority is not authenticated."
)


class OperationalDimension(StrEnum):
    REVIEWER_COMPREHENSION = "reviewer_comprehension"
    AUTOMATION_BIAS = "automation_bias"
    THROUGHPUT = "throughput"
    LATENCY = "latency"
    DOWNTIME = "downtime"
    RECOVERY = "recovery"
    FALLBACK = "fallback"


class OperationalStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class EvaluationStatus(StrEnum):
    EVALUATED = "evaluated"
    ABSTAINED = "abstained"


class OperationalFindingCode(StrEnum):
    COMPREHENSION_FAILURE = "comprehension_failure"
    AUTOMATION_BIAS_RISK = "automation_bias_risk"
    THROUGHPUT_FAILURE = "throughput_failure"
    LATENCY_FAILURE = "latency_failure"
    DOWNTIME_FAILURE = "downtime_failure"
    RECOVERY_FAILURE = "recovery_failure"
    FALLBACK_UNAVAILABLE = "fallback_unavailable"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class OperationalMetric(FrozenModel):
    metric_id: Identifier
    dimension: OperationalDimension
    metric_name: NonEmptyStr
    observed_value: FiniteFloat
    target_value: FiniteFloat
    tolerance: FiniteFloat = Field(ge=0.0)
    sample_size: int = Field(ge=1)
    status: OperationalStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2107_MAX_EVIDENCE)


class FallbackScenario(FrozenModel):
    scenario_id: Identifier
    trigger: NonEmptyStr
    fallback_path: NonEmptyStr
    recovery_seconds: FiniteFloat = Field(ge=0.0)
    fallback_available: bool
    status: OperationalStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2107_MAX_EVIDENCE)

    @model_validator(mode="after")
    def unavailable_fallback_cannot_pass(self) -> FallbackScenario:
        if not self.fallback_available and self.status is OperationalStatus.PASS:
            raise ValueError("unavailable fallback cannot pass operational evaluation")
        return self


class OperationalConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_dimensions: tuple[OperationalDimension, ...] = Field(min_length=7, max_length=7)
    automation_bias_warning_required: Literal[True] = True
    fallback_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2107_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_dimensions_are_required(self) -> OperationalConfiguration:
        if len(set(self.required_dimensions)) != len(self.required_dimensions):
            raise ValueError("required operational dimensions must be unique")
        if set(self.required_dimensions) != set(OperationalDimension):
            raise ValueError("configuration must require all operational dimensions")
        return self


class HumanFactorsOperationalReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    metrics: tuple[OperationalMetric, ...] = Field(min_length=1, max_length=M2107_MAX_METRICS)
    fallbacks: tuple[FallbackScenario, ...] = Field(min_length=1, max_length=M2107_MAX_FALLBACKS)
    configuration: OperationalConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2107_MAX_EVIDENCE)

    @model_validator(mode="after")
    def report_is_closed(self) -> HumanFactorsOperationalReport:
        metric_ids = tuple(item.metric_id for item in self.metrics)
        fallback_ids = tuple(item.scenario_id for item in self.fallbacks)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("operational metric ids must be unique")
        if len(fallback_ids) != len(set(fallback_ids)):
            raise ValueError("fallback scenario ids must be unique")
        dimensions = {item.dimension for item in self.metrics}
        if dimensions != set(self.configuration.required_dimensions):
            raise ValueError("operational report must cover every configured dimension")
        return self


class OperationalFinding(FrozenModel):
    finding_id: Identifier
    code: OperationalFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2107_MAX_EVIDENCE)


class EvaluateComplexActivityHumanFactorsRequest(FrozenModel):
    """Provisional request bound to the M21-06 challenge result."""

    operation: Literal["evaluate_complex_activity_human_factors"] = M2107_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2107_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    metrics: tuple[OperationalMetric, ...] = Field(min_length=1, max_length=M2107_MAX_METRICS)
    fallbacks: tuple[FallbackScenario, ...] = Field(min_length=1, max_length=M2107_MAX_FALLBACKS)
    configuration: OperationalConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2107_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EvaluateComplexActivityHumanFactorsRequest:
        if self.upstream_result.media_type != M2107_M2106_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M21-06 challenge result")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must equal request id")
        metric_ids = tuple(item.metric_id for item in self.metrics)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("request operational metric ids must be unique")
        if {item.dimension for item in self.metrics} != set(self.configuration.required_dimensions):
            raise ValueError("request metrics must cover every configured dimension")
        fallback_ids = tuple(item.scenario_id for item in self.fallbacks)
        if len(fallback_ids) != len(set(fallback_ids)):
            raise ValueError("request fallback scenario ids must be unique")
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("request source artifacts must be unique")
        upstream_key = (
            self.upstream_result.artifact_id,
            self.upstream_result.version,
            self.upstream_result.digest,
            self.upstream_result.media_type,
        )
        if upstream_key not in set(source_keys):
            raise ValueError("request source artifacts must include the M21-06 result")
        return self


class ComplexActivityHumanFactorsResult(FrozenModel):
    """Human-factors and operational validation with safe abstention."""

    output_type: Literal["complex_activity_human_factors"] = "complex_activity_human_factors"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2107_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateComplexActivityHumanFactorsRequest
    status: EvaluationStatus
    report: HumanFactorsOperationalReport | None = None
    findings: tuple[OperationalFinding, ...] = Field(default=(), max_length=M2107_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2107_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2107_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityHumanFactorsResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result id must be deterministically bound to the request")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("result finding ids must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("result evidence must be unique")
        if self.status is EvaluationStatus.EVALUATED:
            if (
                self.report is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported operational report")
            if self.report.configuration != self.request.configuration:
                raise ValueError("evaluated report configuration must equal the request")
            if self.report.metrics != self.request.metrics:
                raise ValueError("evaluated report metrics must equal the request")
            if self.report.fallbacks != self.request.fallbacks:
                raise ValueError("evaluated report fallbacks must equal the request")
        elif (
            self.report is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no report and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2107_CONTRACT_VERSION",
    "M2107_DOSSIER_SHA256",
    "M2107_DOSSIER_SLICE",
    "M2107_EVIDENCE_CLAIM",
    "M2107_GATE",
    "M2107_M2106_INPUT_MEDIA_TYPE",
    "M2107_MAX_CANONICAL_REQUEST_BYTES",
    "M2107_MAX_CANONICAL_RESULT_BYTES",
    "M2107_MAX_EVIDENCE",
    "M2107_MAX_FALLBACKS",
    "M2107_MAX_FINDINGS",
    "M2107_MAX_METRICS",
    "M2107_MODULE_ID",
    "M2107_OPERATION",
    "M2107_OUTPUT_MEDIA_TYPE",
    "M2107_OWNER",
    "M2107_PARENT",
    "M2107_PROVISIONAL_ABI",
    "M2107_SAFETY_CLASS",
    "ComplexActivityHumanFactorsResult",
    "EvaluateComplexActivityHumanFactorsRequest",
    "EvaluationStatus",
    "FallbackScenario",
    "HumanFactorsOperationalReport",
    "OperationalConfiguration",
    "OperationalDimension",
    "OperationalFinding",
    "OperationalFindingCode",
    "OperationalMetric",
    "OperationalStatus",
]
