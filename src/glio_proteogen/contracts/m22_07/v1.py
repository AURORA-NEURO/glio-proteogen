"""Provisional M22-07 human-factors and operational evaluator contracts.

M22-07 evaluates reviewer comprehension, automation bias, throughput, latency,
downtime, recovery and fallback beneath Orthogonal immunoassay validation.  It
emits a human-factors and operational validation report; the ABI is provisional
pending ML engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m22_07.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier SHA
# 0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181,
# lines 7860-7900. Owner confirmation and implementation details remain
# pending. M22-06 is accepted only as a caller-declared media boundary.
M2207_MODULE_ID: Final = "GLIO-PROTEOGEN-M22-07"
M2207_OPERATION: Final = "evaluate_protein_rna_discordance_human_factors_operational"
M2207_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2207_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-07+json"
M2207_M2206_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-06+json"
M2207_PARENT: Final = "protein-RNA discordance"
M2207_OWNER: Final = "ML engineering"
M2207_SAFETY_CLASS: Final = "S3"
M2207_GATE: Final = "G4"
M2207_PROVISIONAL_ABI: Final = True
M2207_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2207_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7860-7900"
M2207_MAX_METRICS: Final = 256
M2207_MAX_FALLBACKS: Final = 64
M2207_MAX_EVIDENCE: Final = 64
M2207_MAX_FINDINGS: Final = 64
M2207_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2207_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2207_EVIDENCE_CLAIM: Final = (
    "Caller-declared M22-07 reviewer-comprehension, automation-bias, throughput, "
    "latency, downtime, recovery and fallback material; issuer authority is not authenticated."
)

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


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
    observed_value: FiniteFloat
    target_value: FiniteFloat
    tolerance: FiniteFloat = Field(ge=0.0)
    sample_size: int = Field(ge=1)
    status: OperationalStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2207_MAX_EVIDENCE)

    @model_validator(mode="after")
    def status_matches_tolerance(self) -> OperationalMetric:
        within_tolerance = abs(self.observed_value - self.target_value) <= self.tolerance
        if self.status is OperationalStatus.PASS and not within_tolerance:
            raise ValueError("passing metric must be within its declared tolerance")
        if self.status is OperationalStatus.FAIL and within_tolerance:
            raise ValueError("failing metric must exceed its declared tolerance")
        return self


class FallbackScenario(FrozenModel):
    """A tested operational recovery or fallback path."""

    scenario_id: Identifier
    dimension: OperationalDimension
    trigger: NonEmptyStr
    fallback_path: NonEmptyStr
    recovery_seconds: FiniteFloat = Field(ge=0.0)
    fallback_available: bool
    status: OperationalStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2207_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2207_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_dimensions_are_required(self) -> OperationalConfiguration:
        if len(set(self.required_dimensions)) != len(self.required_dimensions):
            raise ValueError("required dimensions must be unique")
        if set(self.required_dimensions) != set(OperationalDimension):
            raise ValueError("configuration must require all operational dimensions")
        return self


class HumanFactorsOperationalReport(FrozenModel):
    """Locked operational report with explicit fallback coverage."""

    report_id: Identifier
    version: SemanticVersion
    metrics: tuple[OperationalMetric, ...] = Field(min_length=1, max_length=M2207_MAX_METRICS)
    fallbacks: tuple[FallbackScenario, ...] = Field(min_length=1, max_length=M2207_MAX_FALLBACKS)
    configuration: OperationalConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2207_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2207_MAX_EVIDENCE)


class EvaluateProteinRnaDiscordanceHumanFactorsRequest(FrozenModel):
    """Provisional request for the human-factors and operational evaluation."""

    operation: Literal["evaluate_protein_rna_discordance_human_factors_operational"] = (
        M2207_OPERATION
    )
    contract_version: Literal["0.1.0-provisional"] = M2207_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    metrics: tuple[OperationalMetric, ...] = Field(min_length=1, max_length=M2207_MAX_METRICS)
    fallbacks: tuple[FallbackScenario, ...] = Field(min_length=1, max_length=M2207_MAX_FALLBACKS)
    configuration: OperationalConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2207_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> EvaluateProteinRnaDiscordanceHumanFactorsRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
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
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("request source artifacts must be unique")
        required_sources = {
            (
                item.artifact_id,
                item.version,
                item.digest,
                item.media_type,
            )
            for item in (
                self.mass_spectrometry_proteome,
                self.genome_transcriptome,
                self.ptm_annotations,
            )
        }
        if not required_sources <= set(source_keys):
            raise ValueError("source artifacts must include each declared input")
        upstream_sources = [
            item
            for item in self.source_artifacts
            if item.media_type == M2207_M2206_INPUT_MEDIA_TYPE
        ]
        if len(upstream_sources) != 1:
            raise ValueError("source artifacts must include exactly one M22-06 media boundary")
        return self


class ProteinRnaDiscordanceHumanFactorsResult(FrozenModel):
    """Human-factors and operational result with safe abstention."""

    output_type: Literal["protein_rna_discordance_human_factors_operational"] = (
        "protein_rna_discordance_human_factors_operational"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2207_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateProteinRnaDiscordanceHumanFactorsRequest
    status: EvaluationStatus
    report: HumanFactorsOperationalReport | None = None
    findings: tuple[OperationalFinding, ...] = Field(default=(), max_length=M2207_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein-RNA discordance"] = M2207_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2207_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceHumanFactorsResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result identifier must be derived from request digest")
        if self.status is EvaluationStatus.EVALUATED:
            if (
                self.report is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported operational report")
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
    "M2207_CONTRACT_VERSION",
    "M2207_DOSSIER_SHA256",
    "M2207_DOSSIER_SLICE",
    "M2207_EVIDENCE_CLAIM",
    "M2207_GATE",
    "M2207_M2206_INPUT_MEDIA_TYPE",
    "M2207_MAX_CANONICAL_REQUEST_BYTES",
    "M2207_MAX_CANONICAL_RESULT_BYTES",
    "M2207_MAX_EVIDENCE",
    "M2207_MAX_FALLBACKS",
    "M2207_MAX_FINDINGS",
    "M2207_MAX_METRICS",
    "M2207_MODULE_ID",
    "M2207_OPERATION",
    "M2207_OUTPUT_MEDIA_TYPE",
    "M2207_OWNER",
    "M2207_PARENT",
    "M2207_PROVISIONAL_ABI",
    "M2207_SAFETY_CLASS",
    "EvaluateProteinRnaDiscordanceHumanFactorsRequest",
    "EvaluationStatus",
    "FallbackScenario",
    "FiniteFloat",
    "HumanFactorsOperationalReport",
    "OperationalConfiguration",
    "OperationalDimension",
    "OperationalFinding",
    "OperationalFindingCode",
    "OperationalMetric",
    "OperationalStatus",
    "ProteinRnaDiscordanceHumanFactorsResult",
]
