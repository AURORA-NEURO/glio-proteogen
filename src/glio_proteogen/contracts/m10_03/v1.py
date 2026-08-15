"""Provisional M10-03 mature baseline-estimator contracts.

The dossier requires a transparent, established baseline with locked
preprocessing, tuning, uncertainty, and diagnostics, but does not freeze the
public ABI, estimator catalogue, or performance ceilings.  All symbols are
provisional scaffolding pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m10_03.canonical import (
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

M1003_MODULE_ID: Final = "GLIO-PROTEOGEN-M10-03"
M1003_OPERATION: Final = "estimate_protein_rna_discordance_baseline"
M1003_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1003_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-03+json"
M1003_BASELINE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-01+json"
M1003_PARENT: Final = "protein_rna_discordance"
M1003_OWNER: Final = "ML engineering"
M1003_SAFETY_CLASS: Final = "S2"
M1003_GATE: Final = "G1"
M1003_PROVISIONAL_ABI: Final = True
M1003_MAX_ESTIMATES: Final = 512
M1003_MAX_DIAGNOSTICS: Final = 256
M1003_MAX_PREPROCESSING_STEPS: Final = 64
M1003_MAX_TARGETS: Final = 512
M1003_MAX_EVIDENCE: Final = 32
M1003_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1003_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1003_BENCHMARK_ITERATIONS: Final = 10
M1003_MEAN_BUDGET_NS: Final = 2_000_000_000
M1003_P95_BUDGET_NS: Final = 3_000_000_000
M1003_EVIDENCE_CLAIM: Final = (
    "Caller-declared protein-RNA baseline and benchmark evidence; issuer authority "
    "is not authenticated."
)


class BaselineEstimatorFamily(StrEnum):
    ROBUST_LINEAR = "robust_linear"
    MIXED_EFFECTS = "mixed_effects"
    RULE_BASED = "rule_based"
    ESTABLISHED_STATISTICAL = "established_statistical"


class BaselineEstimateKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"


class BaselineDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class BaselineResultStatus(StrEnum):
    ESTIMATED = "estimated"
    ABSTAINED = "abstained"


class BaselineReplayReason(StrEnum):
    VERIFIED = "verified"
    INVALID_RESULT = "invalid_result"
    DIGEST_MISMATCH = "digest_mismatch"
    NON_CANONICAL = "non_canonical"
    OVERSIZED = "oversized"


class BaselinePreprocessingStep(FrozenModel):
    sequence: int = Field(ge=1, le=M1003_MAX_PREPROCESSING_STEPS)
    operation: NonEmptyStr
    parameters_digest: Sha256Digest
    leakage_safe: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)


class BaselineTuningSpec(FrozenModel):
    tuning_id: Identifier
    protocol: NonEmptyStr
    objective: NonEmptyStr
    folds: int = Field(ge=2, le=1000)
    benchmark_artifact: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)


class BaselineConfiguration(FrozenModel):
    """Locked estimator, preprocessing, tuning, and uncertainty declaration."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: BaselineEstimatorFamily
    target_feature_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M1003_MAX_TARGETS
    )
    preprocessing: tuple[BaselinePreprocessingStep, ...] = Field(
        min_length=1, max_length=M1003_MAX_PREPROCESSING_STEPS
    )
    tuning: BaselineTuningSpec
    uncertainty_method: NonEmptyStr
    reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)

    @model_validator(mode="after")
    def preprocessing_is_ordered(self) -> BaselineConfiguration:
        sequences = tuple(item.sequence for item in self.preprocessing)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("baseline preprocessing steps must have unique ordered sequences")
        return self

    @model_validator(mode="after")
    def targets_are_unique(self) -> BaselineConfiguration:
        if len(set(self.target_feature_ids)) != len(self.target_feature_ids):
            raise ValueError("baseline target feature ids must be unique")
        return self


class BaselineEstimate(FrozenModel):
    feature_id: Identifier
    kind: BaselineEstimateKind
    unit: NonEmptyStr
    estimate_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    category: NonEmptyStr | None = None
    support_score: float = Field(ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_shape_is_closed(self) -> BaselineEstimate:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        if self.kind is BaselineEstimateKind.SCALAR:
            if self.estimate_value is None or has_interval or self.category is not None:
                raise ValueError("scalar baseline requires one scalar value")
        elif self.kind is BaselineEstimateKind.INTERVAL:
            if (
                self.estimate_value is None
                or self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or not self.lower_bound <= self.estimate_value <= self.upper_bound
                or self.category is not None
            ):
                raise ValueError("interval baseline requires ordered bounds and center")
        elif self.category is None or self.estimate_value is not None or has_interval:
            raise ValueError("categorical baseline requires only a category")
        return self


class BaselineDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: BaselineDiagnosticStatus
    metric_name: NonEmptyStr
    metric_value: float | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)


class EstimateProteinRnaDiscordanceBaselineVerification(FrozenModel):
    """Content and deterministic replay status for one baseline result."""

    content_verified: bool
    deterministic_verified: bool
    verified: bool
    result_digest: Sha256Digest | None = None
    reason: BaselineReplayReason

    @model_validator(mode="after")
    def flags_are_closed(self) -> EstimateProteinRnaDiscordanceBaselineVerification:
        expected = self.content_verified and self.deterministic_verified
        if self.verified != expected:
            raise ValueError("verified must equal content and deterministic verification")
        if self.verified != (self.result_digest is not None):
            raise ValueError("verified results must carry a result digest only")
        return self


class EstimateProteinRnaDiscordanceBaselineRequest(FrozenModel):
    """Provisional request bound to the complete M10-01 formal-state result."""

    operation: Literal["estimate_protein_rna_discordance_baseline"] = M1003_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1003_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    formal_state_result: ArtifactReference
    configuration: BaselineConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1003_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateProteinRnaDiscordanceBaselineRequest:
        if self.formal_state_result.media_type != M1003_BASELINE_MEDIA_TYPE:
            raise ValueError("baseline request must bind the provisional M10-01 result")
        return self


class ProteinRnaDiscordanceBaselineResult(FrozenModel):
    """Baseline estimates, uncertainty, diagnostics, and explicit abstention."""

    output_type: Literal["protein_rna_discordance_baseline"] = (
        "protein_rna_discordance_baseline"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1003_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateProteinRnaDiscordanceBaselineRequest
    status: BaselineResultStatus
    estimates: tuple[BaselineEstimate, ...] = Field(default=(), max_length=M1003_MAX_ESTIMATES)
    diagnostics: tuple[BaselineDiagnostic, ...] = Field(
        default=(), max_length=M1003_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1003_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceBaselineResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        failed = {BaselineDiagnosticStatus.FAIL, BaselineDiagnosticStatus.NOT_EVALUABLE}
        if self.status is BaselineResultStatus.ESTIMATED:
            if (
                not self.estimates
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed for item in self.diagnostics)
            ):
                raise ValueError("estimated result requires supported, evaluable baseline")
        elif (
            self.estimates
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimates and safe status")
        estimate_ids = tuple(item.feature_id for item in self.estimates)
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(estimate_ids) != len(set(estimate_ids)):
            raise ValueError("baseline estimate feature ids must be unique")
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("baseline diagnostic ids must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1003_BASELINE_MEDIA_TYPE",
    "M1003_BENCHMARK_ITERATIONS",
    "M1003_CONTRACT_VERSION",
    "M1003_EVIDENCE_CLAIM",
    "M1003_GATE",
    "M1003_MAX_CANONICAL_REQUEST_BYTES",
    "M1003_MAX_CANONICAL_RESULT_BYTES",
    "M1003_MEAN_BUDGET_NS",
    "M1003_MAX_DIAGNOSTICS",
    "M1003_MAX_ESTIMATES",
    "M1003_MAX_EVIDENCE",
    "M1003_MAX_PREPROCESSING_STEPS",
    "M1003_MAX_TARGETS",
    "M1003_MODULE_ID",
    "M1003_OPERATION",
    "M1003_OUTPUT_MEDIA_TYPE",
    "M1003_OWNER",
    "M1003_PARENT",
    "M1003_P95_BUDGET_NS",
    "M1003_PROVISIONAL_ABI",
    "M1003_SAFETY_CLASS",
    "BaselineConfiguration",
    "BaselineDiagnostic",
    "BaselineDiagnosticStatus",
    "BaselineEstimate",
    "BaselineEstimateKind",
    "BaselineEstimatorFamily",
    "BaselinePreprocessingStep",
    "BaselineResultStatus",
    "BaselineReplayReason",
    "BaselineTuningSpec",
    "EstimateProteinRnaDiscordanceBaselineRequest",
    "ProteinRnaDiscordanceBaselineResult",
    "EstimateProteinRnaDiscordanceBaselineVerification",
]
