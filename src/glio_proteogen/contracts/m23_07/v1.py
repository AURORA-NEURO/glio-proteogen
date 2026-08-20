"""Provisional M23-07 human-factors and operational evaluator contracts.

M23-07 evaluates reviewer comprehension, automation bias, throughput, latency,
downtime, recovery and fallback beneath Cross-instrument transport.  It
emits a human-factors and operational validation report; the ABI is provisional
pending Quality engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m23_07.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 8220-8260.
M2307_MODULE_ID: Final = "GLIO-PROTEOGEN-M23-07"
M2307_OPERATION: Final = "evaluate_variant_peptide_human_factors_operational"
M2307_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2307_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m23-07+json"
M2307_M2306_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m23-06+json"
M2307_PARENT: Final = "variant peptide"
M2307_OWNER: Final = "Quality engineering"
M2307_SAFETY_CLASS: Final = "S3"
M2307_GATE: Final = "G4"
M2307_PROVISIONAL_ABI: Final = True
M2307_MAX_METRICS: Final = 256
M2307_MAX_FALLBACKS: Final = 64
M2307_MAX_EVIDENCE: Final = 64
M2307_MAX_FINDINGS: Final = 64
M2307_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2307_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2307_EVIDENCE_CLAIM: Final = (
    "Caller-declared M23-07 human-factors, operational, uncertainty and fallback "
    "material; issuer authority is not authenticated."
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
    """One measured human-factors or operational dimension."""

    metric_id: Identifier
    dimension: OperationalDimension
    metric_name: NonEmptyStr
    observed_value: float
    target_value: float
    tolerance: float = Field(ge=0.0)
    sample_size: int = Field(ge=1)
    status: OperationalStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2307_MAX_EVIDENCE)


class FallbackScenario(FrozenModel):
    """A tested operational recovery or fallback path."""

    scenario_id: Identifier
    dimension: OperationalDimension
    trigger: NonEmptyStr
    fallback_path: NonEmptyStr
    recovery_seconds: float = Field(ge=0.0)
    fallback_available: bool
    status: OperationalStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2307_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2307_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_dimensions_are_required(self) -> OperationalConfiguration:
        if set(self.required_dimensions) != set(OperationalDimension):
            raise ValueError("configuration must require all operational dimensions")
        return self


class HumanFactorsOperationalReport(FrozenModel):
    """Locked operational report with explicit fallback coverage."""

    report_id: Identifier
    version: SemanticVersion
    metrics: tuple[OperationalMetric, ...] = Field(min_length=1, max_length=M2307_MAX_METRICS)
    fallbacks: tuple[FallbackScenario, ...] = Field(min_length=1, max_length=M2307_MAX_FALLBACKS)
    configuration: OperationalConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2307_MAX_EVIDENCE)

    @model_validator(mode="after")
    def report_is_closed(self) -> HumanFactorsOperationalReport:
        metric_ids = tuple(item.metric_id for item in self.metrics)
        fallback_ids = tuple(item.scenario_id for item in self.fallbacks)
        metric_dimensions = {item.dimension for item in self.metrics}
        fallback_dimensions = {item.dimension for item in self.fallbacks}
        required = set(self.configuration.required_dimensions)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("operational metric ids must be unique")
        if len(fallback_ids) != len(set(fallback_ids)):
            raise ValueError("fallback scenario ids must be unique")
        if not required <= metric_dimensions:
            raise ValueError("report must measure every configured operational dimension")
        if (
            not {
                OperationalDimension.DOWNTIME,
                OperationalDimension.RECOVERY,
                OperationalDimension.FALLBACK,
            }
            <= fallback_dimensions
        ):
            raise ValueError("report must cover downtime, recovery and fallback scenarios")
        return self


class OperationalFinding(FrozenModel):
    finding_id: Identifier
    code: OperationalFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2307_MAX_EVIDENCE)


class EvaluateVariantPeptideHumanFactorsRequest(FrozenModel):
    """Provisional request bound to the M23-06 challenge result."""

    operation: Literal["evaluate_variant_peptide_human_factors_operational"] = M2307_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2307_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    metrics: tuple[OperationalMetric, ...] = Field(min_length=1, max_length=M2307_MAX_METRICS)
    fallbacks: tuple[FallbackScenario, ...] = Field(min_length=1, max_length=M2307_MAX_FALLBACKS)
    configuration: OperationalConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2307_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EvaluateVariantPeptideHumanFactorsRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("context must bind the request identifier")
        if self.upstream_result.media_type != M2307_M2306_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M23-06 challenge result")
        metric_ids = tuple(item.metric_id for item in self.metrics)
        fallback_ids = tuple(item.scenario_id for item in self.fallbacks)
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("metric ids must be unique")
        if len(fallback_ids) != len(set(fallback_ids)):
            raise ValueError("fallback scenario ids must be unique")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source artifact ids must be unique")
        if not any(
            artifact.artifact_id == self.upstream_result.artifact_id
            and artifact.digest == self.upstream_result.digest
            and artifact.media_type == self.upstream_result.media_type
            for artifact in self.source_artifacts
        ):
            raise ValueError("source artifacts must retain the bound upstream result")
        required = set(self.configuration.required_dimensions)
        metric_dimensions = {item.dimension for item in self.metrics}
        fallback_dimensions = {item.dimension for item in self.fallbacks}
        if not required <= metric_dimensions:
            raise ValueError("request must measure every configured operational dimension")
        if (
            not {
                OperationalDimension.DOWNTIME,
                OperationalDimension.RECOVERY,
                OperationalDimension.FALLBACK,
            }
            <= fallback_dimensions
        ):
            raise ValueError("request must cover downtime, recovery and fallback scenarios")
        return self


class VariantPeptideHumanFactorsResult(FrozenModel):
    """Human-factors and operational result with safe abstention."""

    output_type: Literal["variant_peptide_human_factors_operational"] = (
        "variant_peptide_human_factors_operational"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2307_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateVariantPeptideHumanFactorsRequest
    status: EvaluationStatus
    report: HumanFactorsOperationalReport | None = None
    findings: tuple[OperationalFinding, ...] = Field(default=(), max_length=M2307_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant peptide"] = M2307_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2307_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideHumanFactorsResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result id does not bind exact request")
        if self.status is EvaluationStatus.EVALUATED:
            if (
                self.report is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported operational report")
            if (
                self.report.version != self.request.configuration.version
                or self.report.configuration != self.request.configuration
                or self.report.metrics != self.request.metrics
                or self.report.fallbacks != self.request.fallbacks
            ):
                raise ValueError("evaluated report must bind the exact request declarations")
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
    "M2307_CONTRACT_VERSION",
    "M2307_EVIDENCE_CLAIM",
    "M2307_GATE",
    "M2307_M2306_INPUT_MEDIA_TYPE",
    "M2307_MAX_CANONICAL_REQUEST_BYTES",
    "M2307_MAX_CANONICAL_RESULT_BYTES",
    "M2307_MAX_EVIDENCE",
    "M2307_MAX_FALLBACKS",
    "M2307_MAX_FINDINGS",
    "M2307_MAX_METRICS",
    "M2307_MODULE_ID",
    "M2307_OPERATION",
    "M2307_OUTPUT_MEDIA_TYPE",
    "M2307_OWNER",
    "M2307_PARENT",
    "M2307_PROVISIONAL_ABI",
    "M2307_SAFETY_CLASS",
    "EvaluateVariantPeptideHumanFactorsRequest",
    "EvaluationStatus",
    "FallbackScenario",
    "HumanFactorsOperationalReport",
    "OperationalConfiguration",
    "OperationalDimension",
    "OperationalFinding",
    "OperationalFindingCode",
    "OperationalMetric",
    "OperationalStatus",
    "VariantPeptideHumanFactorsResult",
]
