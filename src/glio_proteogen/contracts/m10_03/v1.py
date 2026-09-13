"""Provisional M10-03 mature baseline-estimator contracts.

The dossier requires a transparent, established baseline with locked
preprocessing, tuning, uncertainty, and diagnostics, but does not freeze the
public ABI, estimator catalogue, or performance ceilings.  All symbols are
provisional scaffolding pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
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
M1003_MAX_TYPED_OBSERVATIONS: Final = 512
M1003_MAX_TYPED_EFFECT: Final = 20.0
M1003_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M1003_MAX_BOOTSTRAP_REPLICATES: Final = 256
M1003_GLIOMA_MODEL_FAMILY: Final = "glioma-protein-rna-discordance-programs/1.0.0"


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


class DiscordanceEvidenceState(StrEnum):
    """How a paired protein/RNA observation contributes to the fit."""

    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class GliomaDiscordanceProgram(StrEnum):
    """Glioma programs used for hierarchical protein/RNA discordance shrinkage."""

    RTK_PI3K_AKT_MTOR = "RTK_PI3K_AKT_MTOR"
    P53_CELL_CYCLE = "P53_CELL_CYCLE"
    IDH_HIF1A = "IDH_HIF1A"
    MESENCHYMAL_PROGRAM = "MESENCHYMAL_PROGRAM"
    PROLIFERATION = "PROLIFERATION"


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


class TypedProteinRnaObservation(FrozenModel):
    """Explicit paired protein/RNA effects for the research discordance lane."""

    observation_id: Identifier
    feature_id: Identifier
    program: GliomaDiscordanceProgram | None = None
    evidence_state: DiscordanceEvidenceState
    protein_effect: float | None = Field(
        default=None, ge=-M1003_MAX_TYPED_EFFECT, le=M1003_MAX_TYPED_EFFECT
    )
    rna_effect: float | None = Field(
        default=None, ge=-M1003_MAX_TYPED_EFFECT, le=M1003_MAX_TYPED_EFFECT
    )
    protein_standard_error: float | None = Field(
        default=None, gt=0.0, le=M1003_MAX_TYPED_EFFECT
    )
    rna_standard_error: float | None = Field(default=None, gt=0.0, le=M1003_MAX_TYPED_EFFECT)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)

    @model_validator(mode="after")
    def paired_measurement_shape_is_closed(self) -> TypedProteinRnaObservation:
        active = self.evidence_state in {
            DiscordanceEvidenceState.OBSERVED,
            DiscordanceEvidenceState.LEFT_CENSORED,
        }
        if active:
            if (
                self.program is None
                or self.protein_effect is None
                or self.rna_effect is None
                or self.protein_standard_error is None
                or self.rna_standard_error is None
            ):
                raise ValueError(
                    "active paired evidence requires program, protein/RNA effects, and "
                    "standard errors"
                )
            if self.quality_weight <= 0.0:
                raise ValueError("active paired evidence requires positive quality weight")
        elif (
            self.program is not None
            or self.protein_effect is not None
            or self.rna_effect is not None
            or self.protein_standard_error is not None
            or self.rna_standard_error is not None
            or self.quality_weight != 0.0
        ):
            raise ValueError("missing or unsupported paired evidence cannot carry a value")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("paired protein/RNA evidence must use the evidence role")
        return self


class BaselineConfiguration(FrozenModel):
    """Locked estimator, preprocessing, tuning, and uncertainty declaration."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: BaselineEstimatorFamily
    target_feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1003_MAX_TARGETS)
    preprocessing: tuple[BaselinePreprocessingStep, ...] = Field(
        min_length=1, max_length=M1003_MAX_PREPROCESSING_STEPS
    )
    tuning: BaselineTuningSpec
    uncertainty_method: NonEmptyStr
    bootstrap_replicates: int = Field(
        default=M1003_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M1003_MAX_BOOTSTRAP_REPLICATES,
    )
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
    evidence_count: int = Field(default=0, ge=0, le=M1003_MAX_TYPED_OBSERVATIONS)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    top_drivers: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    ablation_effects: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_shape_is_closed(self) -> BaselineEstimate:
        numeric_values = (
            self.estimate_value,
            self.lower_bound,
            self.upper_bound,
            self.support_score,
        )
        if any(value is not None and not isfinite(value) for value in numeric_values):
            raise ValueError("baseline numeric fields must be finite")
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
    model_family: NonEmptyStr | None = None
    objective_trace_digest: Sha256Digest | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1003_MAX_EVIDENCE)

    @model_validator(mode="after")
    def metric_is_finite(self) -> BaselineDiagnostic:
        if self.metric_value is not None and not isfinite(self.metric_value):
            raise ValueError("diagnostic metric must be finite")
        return self


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
    typed_observations: tuple[TypedProteinRnaObservation, ...] = Field(
        default=(), max_length=M1003_MAX_TYPED_OBSERVATIONS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateProteinRnaDiscordanceBaselineRequest:
        if self.formal_state_result.media_type != M1003_BASELINE_MEDIA_TYPE:
            raise ValueError("baseline request must bind the provisional M10-01 result")
        if self.typed_observations:
            observation_ids = tuple(item.observation_id for item in self.typed_observations)
            if len(observation_ids) != len(set(observation_ids)):
                raise ValueError("typed protein/RNA observation identifiers must be unique")
            feature_ids = tuple(item.feature_id for item in self.typed_observations)
            if len(feature_ids) != len(set(feature_ids)):
                raise ValueError("typed protein/RNA feature identifiers must be unique")
            if not set(feature_ids).issubset(self.configuration.target_feature_ids):
                raise ValueError("typed protein/RNA features must be configured targets")
        return self


class ProteinRnaDiscordanceBaselineResult(FrozenModel):
    """Baseline estimates, uncertainty, diagnostics, and explicit abstention."""

    output_type: Literal["protein_rna_discordance_baseline"] = "protein_rna_discordance_baseline"
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
    "M1003_DEFAULT_BOOTSTRAP_REPLICATES",
    "M1003_EVIDENCE_CLAIM",
    "M1003_GATE",
    "M1003_GLIOMA_MODEL_FAMILY",
    "M1003_MAX_BOOTSTRAP_REPLICATES",
    "M1003_MAX_CANONICAL_REQUEST_BYTES",
    "M1003_MAX_CANONICAL_RESULT_BYTES",
    "M1003_MAX_DIAGNOSTICS",
    "M1003_MAX_ESTIMATES",
    "M1003_MAX_EVIDENCE",
    "M1003_MAX_PREPROCESSING_STEPS",
    "M1003_MAX_TARGETS",
    "M1003_MAX_TYPED_EFFECT",
    "M1003_MAX_TYPED_OBSERVATIONS",
    "M1003_MEAN_BUDGET_NS",
    "M1003_MODULE_ID",
    "M1003_OPERATION",
    "M1003_OUTPUT_MEDIA_TYPE",
    "M1003_OWNER",
    "M1003_P95_BUDGET_NS",
    "M1003_PARENT",
    "M1003_PROVISIONAL_ABI",
    "M1003_SAFETY_CLASS",
    "BaselineConfiguration",
    "BaselineDiagnostic",
    "BaselineDiagnosticStatus",
    "BaselineEstimate",
    "BaselineEstimateKind",
    "BaselineEstimatorFamily",
    "BaselinePreprocessingStep",
    "BaselineReplayReason",
    "BaselineResultStatus",
    "BaselineTuningSpec",
    "DiscordanceEvidenceState",
    "EstimateProteinRnaDiscordanceBaselineRequest",
    "EstimateProteinRnaDiscordanceBaselineVerification",
    "GliomaDiscordanceProgram",
    "ProteinRnaDiscordanceBaselineResult",
    "TypedProteinRnaObservation",
]
