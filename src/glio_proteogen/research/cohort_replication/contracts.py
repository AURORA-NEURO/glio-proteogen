"""Strict aggregate-only contracts for exploratory cohort replication."""

from __future__ import annotations

from math import isfinite
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

ALGORITHM_ID: Final = "glioma-cohort-replication"
ALGORITHM_VERSION: Final = "1.0.0"
PROFILE_ID: Final = "glioma-cohort-replication/1.0.0"
MAX_REQUEST_BYTES: Final = 2_097_152
MAX_RESULT_BYTES: Final = 4_194_304
MAX_REPLAY_BYTES: Final = 8_388_608

type DiseaseContext = Literal[
    "glioblastoma_idh_wildtype",
    "astrocytoma_idh_mutant",
    "oligodendroglioma_idh_mutant_1p19q_codeleted",
    "other_glioma",
]
type EffectScale = Literal[
    "standardized_mean_difference", "log2_ratio", "fisher_z", "standardized_regression_coefficient"
]


class CohortReceipt(FrozenModel):
    cohort_id: Identifier
    label: NonEmptyStr
    source_sha256: Sha256Digest
    independence_group: Identifier
    sample_size: int = Field(ge=2, le=1_000_000)


class CohortEffect(FrozenModel):
    cohort_id: Identifier
    state: Literal["observed", "missing", "unsupported"]
    estimate: float | None = Field(default=None, ge=-100.0, le=100.0)
    standard_error: float | None = Field(default=None, ge=0.000001, le=100.0)

    @model_validator(mode="after")
    def numbers_match_state(self) -> Self:
        if self.state == "observed":
            if self.estimate is None or self.standard_error is None:
                raise ValueError("observed effects require an estimate and standard error")
        elif self.estimate is not None or self.standard_error is not None:
            raise ValueError("missing and unsupported effects cannot contain numbers")
        return self


class FeatureRequest(FrozenModel):
    feature_id: Identifier
    label: NonEmptyStr
    effects: tuple[CohortEffect, ...] = Field(min_length=2, max_length=16)


class ReplicationRequest(FrozenModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    analysis_id: Identifier
    disease_context: DiseaseContext
    estimand_id: Identifier
    effect_scale: EffectScale
    contrast: NonEmptyStr
    independence_basis: Literal["caller_declared_disjoint_participants"] = (
        "caller_declared_disjoint_participants"
    )
    cohorts: tuple[CohortReceipt, ...] = Field(min_length=2, max_length=16)
    features: tuple[FeatureRequest, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def rectangular_independent_canonical_matrix(self) -> Self:
        for field in ("cohort_id", "source_sha256", "independence_group"):
            values = [getattr(cohort, field) for cohort in self.cohorts]
            if len(values) != len(set(values)):
                raise ValueError(f"cohorts must have unique {field} values")
        feature_ids = [feature.feature_id for feature in self.features]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("feature identifiers must be unique")
        cohort_ids = {cohort.cohort_id for cohort in self.cohorts}
        features = []
        for feature in self.features:
            effect_ids = [effect.cohort_id for effect in feature.effects]
            if len(effect_ids) != len(cohort_ids) or set(effect_ids) != cohort_ids:
                raise ValueError("every feature must contain each declared cohort exactly once")
            features.append(
                feature.model_copy(
                    update={"effects": tuple(sorted(feature.effects, key=lambda e: e.cohort_id))}
                )
            )
        object.__setattr__(self, "cohorts", tuple(sorted(self.cohorts, key=lambda c: c.cohort_id)))
        object.__setattr__(self, "features", tuple(sorted(features, key=lambda f: f.feature_id)))
        return self

    @property
    def request_digest(self) -> str:
        from .canonical import canonical_request_digest  # noqa: PLC0415

        return canonical_request_digest(self)


class MetaEstimate(FrozenModel):
    estimate: float
    standard_error: float = Field(gt=0)
    lower: float
    upper: float
    p_value: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def interval_contains_estimate(self) -> Self:
        if not self.lower <= self.estimate <= self.upper:
            raise ValueError("nominal interval must contain its estimate")
        return self


class Heterogeneity(FrozenModel):
    q: float = Field(ge=0)
    degrees_of_freedom: int = Field(ge=1, le=15)
    i_squared_percent: float = Field(ge=0, le=100)
    tau_squared: float = Field(ge=0)


class PredictionInterval(FrozenModel):
    lower: float
    upper: float
    method: Literal["approximate_normal_random_effects"] = "approximate_normal_random_effects"

    @model_validator(mode="after")
    def ordered_interval(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("prediction interval must be ordered")
        return self


class LeaveOneOut(FrozenModel):
    omitted_cohort_id: Identifier
    observed_count: int = Field(ge=2, le=15)
    random_effect: MetaEstimate
    delta_estimate: float


class DirectionAgreement(FrozenModel):
    positive_count: int = Field(ge=0, le=16)
    negative_count: int = Field(ge=0, le=16)
    zero_count: int = Field(ge=0, le=16)
    majority_fraction: float | None = Field(default=None, ge=0, le=1)
    classification: Literal[
        "all_nominal_intervals_positive",
        "all_nominal_intervals_negative",
        "mixed_directions",
        "direction_indeterminate",
    ]


class FeatureResult(FrozenModel):
    feature_id: Identifier
    label: NonEmptyStr
    effects: tuple[CohortEffect, ...] = Field(min_length=2, max_length=16)
    observed_count: int = Field(ge=0, le=16)
    total_count: int = Field(ge=2, le=16)
    support: Literal["limited", "abstained"]
    fixed_effect: MetaEstimate | None
    random_effect: MetaEstimate | None
    heterogeneity: Heterogeneity | None
    prediction_interval: PredictionInterval | None
    p_value: float | None = Field(ge=0, le=1)
    adjusted_p_value: float = Field(ge=0, le=1)
    dependence_robust_adjusted_p_value: float = Field(ge=0, le=1)
    leave_one_out: tuple[LeaveOneOut, ...] = Field(max_length=16)
    direction_agreement: DirectionAgreement
    reasons: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def support_reconciles_with_evidence(self) -> Self:
        count = sum(effect.state == "observed" for effect in self.effects)
        if self.observed_count != count or self.total_count != len(self.effects):
            raise ValueError("feature coverage counts do not reconcile")
        aggregates = (self.fixed_effect, self.random_effect, self.heterogeneity, self.p_value)
        if count < 2:
            if self.support != "abstained" or any(value is not None for value in aggregates):
                raise ValueError("fewer than two observations must abstain from pooling")
            if self.adjusted_p_value != 1.0 or self.dependence_robust_adjusted_p_value != 1.0:
                raise ValueError("abstained features remain in the family with adjusted p=1")
        elif self.support != "limited" or any(value is None for value in aggregates):
            raise ValueError("estimable aggregate evidence must remain limited")
        if count < 3 and (self.prediction_interval is not None or self.leave_one_out):
            raise ValueError("prediction intervals and leave-one-out require three cohorts")
        return self


class ReplicationLimits(FrozenModel):
    max_cohorts: Literal[16] = 16
    max_features: Literal[256] = 256
    request_bytes: Literal[2097152] = MAX_REQUEST_BYTES
    result_bytes: Literal[4194304] = MAX_RESULT_BYTES
    replay_bytes: Literal[8388608] = MAX_REPLAY_BYTES


class ReplicationProfile(FrozenModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["glioma-cohort-replication/1.0.0"] = PROFILE_ID
    algorithm_id: Literal["glioma-cohort-replication"] = ALGORITHM_ID
    algorithm_version: Literal["1.0.0"] = ALGORITHM_VERSION
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    methods: tuple[NonEmptyStr, ...]
    assumptions: tuple[NonEmptyStr, ...]
    limits: ReplicationLimits
    synthetic_demo_only: Literal[True] = True


class ReplicationResult(FrozenModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["glioma-cohort-replication/1.0.0"] = PROFILE_ID
    profile_digest: Sha256Digest
    analysis_id: Identifier
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    disease_context: DiseaseContext
    estimand_id: Identifier
    effect_scale: EffectScale
    contrast: NonEmptyStr
    independence_basis: Literal["caller_declared_disjoint_participants"]
    cohorts: tuple[CohortReceipt, ...] = Field(min_length=2, max_length=16)
    features: tuple[FeatureResult, ...] = Field(min_length=1, max_length=256)
    family_size: int = Field(ge=1, le=256)
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1)
    contains_participant_data: Literal[False] = False

    @model_validator(mode="after")
    def fixed_family_is_complete(self) -> Self:
        if self.family_size != len(self.features):
            raise ValueError("family size must include all predeclared features")
        return self


class ReplayRequest(FrozenModel):
    request: ReplicationRequest
    result: ReplicationResult


class ReplayResult(FrozenModel):
    valid: bool
    request_digest: Sha256Digest
    result_digest: Sha256Digest


def require_finite(value: float) -> float:
    """Prevent a future algorithm change from sealing non-finite output."""

    if not isfinite(value):
        raise ValueError("replication computation produced a non-finite value")
    return value
