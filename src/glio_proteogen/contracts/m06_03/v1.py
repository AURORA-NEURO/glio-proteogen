"""Provisional M06-03 mature-baseline estimator contracts.

The dossier specifies a transparent baseline, locked preprocessing/tuning, and
diagnostics, but does not freeze the estimator ABI, feature catalogue, metric
set, media type, endpoint, or CLI.  The symbols below are provisional scaffolding
only and must not be treated as a production contract.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

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
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0603_MAX_EVIDENCE)


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
    "M0603_EVIDENCE_CLAIM",
    "M0603_GATE",
    "M0603_MAX_CANONICAL_REQUEST_BYTES",
    "M0603_MAX_CANONICAL_RESULT_BYTES",
    "M0603_MAX_DIAGNOSTICS",
    "M0603_MAX_ESTIMATES",
    "M0603_MAX_EVIDENCE",
    "M0603_MAX_FEATURES",
    "M0603_MAX_METRICS",
    "M0603_MAX_PREPROCESSING_STEPS",
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
    "MatureBaselineConfiguration",
]
