"""Provisional M06-03 mature-baseline estimator contracts.

The dossier specifies a transparent baseline, locked preprocessing/tuning, and
diagnostics, but does not freeze the estimator ABI, feature catalogue, metric
set, media type, endpoint, or CLI.  The symbols below are provisional scaffolding
only and must not be treated as a production contract.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from glio_proteogen.contracts.m06_01.canonical import canonical_request_digest
from glio_proteogen.contracts.m06_01.v1 import (
    FormalProteinStateSchema,  # noqa: TC001
    FormalStateFeatureValue,  # noqa: TC001
    ValidateFormalProteinStateResult,  # noqa: TC001
)
from glio_proteogen.contracts.m06_03.canonical import result_payload_digest
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

# PROVISIONAL ABI: inferred solely from the M06-03 dossier slice.
M0603_MODULE_ID: Final = "GLIO-PROTEOGEN-M06-03"
M0603_OPERATION: Final = "estimate_protein_abundance_baseline"
M0603_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0603_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m06-03+json"
M0603_PARENT: Final = "biomarker_panel"
M0603_OWNER: Final = "Platform engineering"
M0603_SAFETY_CLASS: Final = "S2"
M0603_GATE: Final = "G1"
M0603_MAX_FEATURES: Final = 512
M0603_MAX_ESTIMATES: Final = M0603_MAX_FEATURES
M0603_MAX_DIAGNOSTICS: Final = 512
M0603_MAX_PREPROCESSING_STEPS: Final = 64
M0603_MAX_METRICS: Final = 64
M0603_MAX_EVIDENCE: Final = 32
M0603_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0603_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0603_MAX_PROGRAM_STATES: Final = 5
M0603_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M0603_MAX_BOOTSTRAP_REPLICATES: Final = 256
M0603_BENCHMARK_ITERATIONS: Final = 25
M0603_BENCHMARK_WARMUPS: Final = 1
M0603_MEAN_BUDGET_NS: Final = 500_000_000
M0603_P95_BUDGET_NS: Final = 750_000_000
M0603_EVIDENCE_CLAIM: Final = (
    "Caller-declared mature-baseline evidence; issuer authority is not authenticated."
)


class BaselineEstimatorFamily(StrEnum):
    RULE_BASED = "rule_based"
    ROBUST_STATISTICAL = "robust_statistical"
    ESTABLISHED_COMPUTATIONAL = "established_computational"


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


class GliomaBaselineProgram(StrEnum):
    """Glioma programs used by the research-only abundance baseline lane."""

    RTK_PI3K_AKT_MTOR = "RTK_PI3K_AKT_MTOR"
    P53_CELL_CYCLE = "P53_CELL_CYCLE"
    IDH_HIF1A = "IDH_HIF1A"
    MESENCHYMAL_PROGRAM = "MESENCHYMAL_PROGRAM"
    PROLIFERATION = "PROLIFERATION"


class BaselinePreprocessingPolicy(FrozenModel):
    """Locked, caller-declared preprocessing steps for the baseline."""

    policy_id: Identifier
    version: SemanticVersion
    operations: tuple[NonEmptyStr, ...] = Field(
        min_length=1,
        max_length=M0603_MAX_PREPROCESSING_STEPS,
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)


class BaselineTuningRecord(FrozenModel):
    """Locked baseline tuning declaration; no tuning is performed by the contract."""

    tuning_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    objective: NonEmptyStr
    seed: int = Field(ge=0)
    metrics: tuple[NonEmptyStr, ...] = Field(default=(), max_length=M0603_MAX_METRICS)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)


class GliomaFeatureAnnotation(FrozenModel):
    """A caller-declared feature-to-program mapping for the research lane."""

    feature_id: Identifier
    program: GliomaBaselineProgram
    direction: Literal[-1, 1] = 1
    standard_error: float = Field(default=1.0, gt=0.0, le=100.0, allow_inf_nan=False)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0, allow_inf_nan=False)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)

    @model_validator(mode="after")
    def annotation_is_informative(self) -> GliomaFeatureAnnotation:
        if self.quality_weight <= 0.0:
            raise ValueError("glioma feature annotation requires positive quality")
        return self


class MatureBaselineConfiguration(FrozenModel):
    """Versioned estimator configuration bound to the M06-01 state schema."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: BaselineEstimatorFamily
    state_schema_id: Identifier
    state_schema_version: SemanticVersion
    preprocessing: BaselinePreprocessingPolicy
    tuning: BaselineTuningRecord
    reference: ArtifactReference
    glioma_annotations: tuple[GliomaFeatureAnnotation, ...] = Field(
        default=(), max_length=M0603_MAX_FEATURES
    )
    bootstrap_replicates: int = Field(
        default=M0603_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M0603_MAX_BOOTSTRAP_REPLICATES,
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)

    @model_validator(mode="after")
    def annotations_are_unique(self) -> MatureBaselineConfiguration:
        ids = tuple(item.feature_id for item in self.glioma_annotations)
        if len(ids) != len(set(ids)):
            raise ValueError("glioma feature annotations must be unique")
        return self


class BaselineEstimate(FrozenModel):
    """One aggregate baseline estimate; raw spectra and external content are absent."""

    feature_id: Identifier
    kind: BaselineEstimateKind
    unit: NonEmptyStr
    estimate_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    category: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_shape_is_closed(self) -> BaselineEstimate:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        if self.kind is BaselineEstimateKind.SCALAR:
            if self.estimate_value is None or has_interval or self.category is not None:
                raise ValueError("scalar baseline estimate requires one scalar value")
        elif self.kind is BaselineEstimateKind.INTERVAL:
            if (
                self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or self.estimate_value is None
                or self.category is not None
            ):
                raise ValueError("interval baseline estimate requires ordered bounds and center")
            if not self.lower_bound <= self.estimate_value <= self.upper_bound:
                raise ValueError("interval center must lie within its bounds")
        elif (
            self.category is None
            or self.estimate_value is not None
            or has_interval
        ):
            raise ValueError("categorical baseline estimate requires only a category")
        return self


class BaselineDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: BaselineDiagnosticStatus
    message: NonEmptyStr
    metric_name: NonEmptyStr | None = None
    metric_value: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)


class GliomaProgramBaselineState(FrozenModel):
    """Robust, normalized research state for one glioma program."""

    program: GliomaBaselineProgram
    score: float
    lower_bound: float
    upper_bound: float
    stability: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    discordance: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    evidence_count: int = Field(ge=1, le=M0603_MAX_FEATURES)
    top_drivers: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    ablation_effects: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)

    @field_validator("score", "lower_bound", "upper_bound")
    @classmethod
    def state_values_are_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("glioma baseline state values must be finite")
        return value

    @model_validator(mode="after")
    def state_bounds_are_closed(self) -> GliomaProgramBaselineState:
        if self.lower_bound > self.upper_bound or not (
            self.lower_bound <= self.score <= self.upper_bound
        ):
            raise ValueError("glioma baseline state requires ordered bounds containing score")
        return self


class EstimateProteinAbundanceBaselineRequest(FrozenModel):
    """Provisional request ABI for the mature-baseline estimator."""

    operation: Literal["estimate_protein_abundance_baseline"] = M0603_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0603_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    formal_state_result: ValidateFormalProteinStateResult
    state_schema: FormalProteinStateSchema
    feature_values: tuple[FormalStateFeatureValue, ...] = Field(
        min_length=1,
        max_length=M0603_MAX_FEATURES,
    )
    configuration: MatureBaselineConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0603_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateProteinAbundanceBaselineRequest:
        if self.formal_state_result.request.state_schema != self.state_schema:
            raise ValueError("baseline request must preserve the complete M06-01 state schema")
        if self.formal_state_result.request.values != self.feature_values:
            raise ValueError("baseline request must preserve the complete M06-01 feature values")
        schema_features = {item.feature_id for item in self.state_schema.features}
        value_features = {item.feature_id for item in self.feature_values}
        if len(value_features) != len(self.feature_values):
            raise ValueError("baseline request feature values must be unique")
        if value_features != schema_features:
            raise ValueError("baseline request must cover the complete formal-state schema")
        if (
            self.configuration.state_schema_id != self.state_schema.schema_id
            or self.configuration.state_schema_version != self.state_schema.version
        ):
            raise ValueError("baseline configuration does not bind the formal-state schema")
        annotation_ids = {item.feature_id for item in self.configuration.glioma_annotations}
        if not annotation_ids <= schema_features:
            raise ValueError("glioma baseline annotation references an unknown feature")
        return self


class EstimateProteinAbundanceBaselineResult(FrozenModel):
    """Provisional baseline result with explicit abstention and diagnostics."""

    output_type: Literal["protein_abundance_baseline_estimate"] = (
        "protein_abundance_baseline_estimate"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0603_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateProteinAbundanceBaselineRequest
    status: BaselineResultStatus
    estimates: tuple[BaselineEstimate, ...] = Field(
        default=(), max_length=M0603_MAX_ESTIMATES
    )
    program_states: tuple[GliomaProgramBaselineState, ...] = Field(
        default=(), max_length=M0603_MAX_PROGRAM_STATES
    )
    diagnostics: tuple[BaselineDiagnostic, ...] = Field(
        default=(), max_length=M0603_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker_panel"] = M0603_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> EstimateProteinAbundanceBaselineResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is BaselineResultStatus.ESTIMATED:
            if not self.estimates or self.abstention_reason is not None:
                raise ValueError("estimated result requires estimates and no abstention reason")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("estimated result requires supported status")
        elif (
            self.estimates
            or self.program_states
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimates, a reason, and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0603_BENCHMARK_ITERATIONS",
    "M0603_BENCHMARK_WARMUPS",
    "M0603_CONTRACT_VERSION",
    "M0603_DEFAULT_BOOTSTRAP_REPLICATES",
    "M0603_EVIDENCE_CLAIM",
    "M0603_GATE",
    "M0603_MAX_BOOTSTRAP_REPLICATES",
    "M0603_MAX_CANONICAL_REQUEST_BYTES",
    "M0603_MAX_CANONICAL_RESULT_BYTES",
    "M0603_MAX_DIAGNOSTICS",
    "M0603_MAX_ESTIMATES",
    "M0603_MAX_EVIDENCE",
    "M0603_MAX_FEATURES",
    "M0603_MAX_METRICS",
    "M0603_MAX_PREPROCESSING_STEPS",
    "M0603_MAX_PROGRAM_STATES",
    "M0603_MEAN_BUDGET_NS",
    "M0603_MODULE_ID",
    "M0603_OPERATION",
    "M0603_OUTPUT_MEDIA_TYPE",
    "M0603_OWNER",
    "M0603_P95_BUDGET_NS",
    "M0603_PARENT",
    "M0603_SAFETY_CLASS",
    "BaselineDiagnostic",
    "BaselineDiagnosticStatus",
    "BaselineEstimate",
    "BaselineEstimateKind",
    "BaselineEstimatorFamily",
    "BaselinePreprocessingPolicy",
    "BaselineResultStatus",
    "BaselineTuningRecord",
    "EstimateProteinAbundanceBaselineRequest",
    "EstimateProteinAbundanceBaselineResult",
    "GliomaBaselineProgram",
    "GliomaFeatureAnnotation",
    "GliomaProgramBaselineState",
    "MatureBaselineConfiguration",
]
