"""Strict contracts for longitudinal GBM complex-member transition concordance.

The lane estimates a robust latent coordinate over proteins annotated as members
of a fixed Reactome participant set.  It does not estimate physical assembly,
stoichiometry, occupancy, biochemical activity, causality, prognosis, or therapy
response.  Those exclusions are part of the machine-readable result contract.
"""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise
from typing import Literal, Self, cast

from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from glio_proteogen.research.longitudinal_gbm.contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    AssayCompatibilityAttestation,
    LongitudinalTimePoint,
    NormalizationReference,
    ProteinEvidenceState,
    ProteinObservation,
)

from .canonical import canonical_request_digest, profile_payload_digest, result_payload_digest

ALGORITHM_ID = "kncc-reactome-complex-transition"
ALGORITHM_VERSION = "1.0.0"
PROFILE_ID = "kncc-reactome-complex-transition/1.0.0"
MODEL_ID = "kncc-reactome-complex-transition-factor-model/1.0.0"

MIN_TIME_POINTS = 2
MAX_TIME_POINTS = 16
MAX_OBSERVATIONS_PER_TIME_POINT = 4_096
MAX_TOTAL_OBSERVATIONS = 12_000
MIN_BOOTSTRAPS = 32
DEFAULT_BOOTSTRAPS = 64
MAX_BOOTSTRAPS = 256
MAX_COMPLEXES = 64
MAX_MEMBERS_PER_COMPLEX = 32
MAX_TOP_CONTRIBUTIONS = 8
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 4 * 1_024 * 1_024
MAX_REPLAY_BYTES = 8 * 1_024 * 1_024

MIN_ACTIVE_MEMBERS = 3
MIN_MEMBER_RELIABILITY = 0.05
MIN_COEFFICIENT_MASS = 0.50
MIN_EFFECTIVE_SAMPLE_SIZE = 2.0
SUPPORTED_MIN_STABILITY = 0.80
SUPPORTED_MIN_LOADING_COSINE = 0.80


class AnalysisSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class ComplexTransitionClassification(StrEnum):
    SOURCE_RECURRENCE_ALIGNED = "source_recurrence_aligned"
    SOURCE_PRIMARY_ALIGNED = "source_primary_aligned"
    STABLE = "stable"
    INDETERMINATE = "indeterminate"
    NOT_ESTIMABLE = "not_estimable"


class UncertaintyState(StrEnum):
    ESTIMATED = "estimated"
    NOT_ESTIMABLE = "not_estimable"


class ValueSemantics(StrEnum):
    EXACT_DELTA = "exact_delta"
    UPPER_BOUND = "upper_bound"
    LOWER_BOUND = "lower_bound"


class ContributionDirection(StrEnum):
    SOURCE_RECURRENCE_ALIGNED = "source_recurrence_aligned"
    SOURCE_PRIMARY_ALIGNED = "source_primary_aligned"


class LongitudinalGbmComplexTransitionRequest(FrozenModel):
    """One caller-owned ordered protein series on the locked KNCC assay scale."""

    profile_id: Literal["kncc-reactome-complex-transition/1.0.0"] = (
        "kncc-reactome-complex-transition/1.0.0"
    )
    series_id: Identifier
    assay_compatibility: AssayCompatibilityAttestation
    normalization_reference: NormalizationReference
    time_points: tuple[LongitudinalTimePoint, ...] = Field(
        min_length=MIN_TIME_POINTS,
        max_length=MAX_TIME_POINTS,
    )
    bootstrap_replicates: int = Field(
        default=DEFAULT_BOOTSTRAPS,
        ge=MIN_BOOTSTRAPS,
        le=MAX_BOOTSTRAPS,
    )

    @model_validator(mode="after")
    def series_is_ordered_unique_and_reference_bound(self) -> Self:
        point_ids = tuple(point.time_point_id for point in self.time_points)
        if len(point_ids) != len(set(point_ids)):
            raise ValueError("longitudinal time-point identifiers must be unique")
        offsets = tuple(point.time_offset_days for point in self.time_points)
        if any(left >= right for left, right in pairwise(offsets)):
            raise ValueError("time offsets must be strictly increasing in request order")
        expected_reference = self.normalization_reference.binding_digest
        if any(
            point.normalization_reference_digest != expected_reference for point in self.time_points
        ):
            raise ValueError(
                "every time point must use the invariant request normalization/reference digest"
            )
        observation_ids = tuple(
            observation.observation_id
            for point in self.time_points
            for observation in point.observations
        )
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation identifiers must be unique across the series")
        if len(observation_ids) > MAX_TOTAL_OBSERVATIONS:
            raise ValueError(
                f"complex-transition requests are limited to {MAX_TOTAL_OBSERVATIONS} observations"
            )
        return self

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class ComplexTransitionUncertainty(FrozenModel):
    state: UncertaintyState
    measurement_standard_error: float | None = Field(default=None, ge=0.0)
    fitted_model_standard_error: float | None = Field(default=None, ge=0.0)
    measurement_model_covariance: float | None = None
    combined_standard_error: float | None = Field(default=None, ge=0.0)
    variance_closure_residual: float | None = Field(default=None, ge=0.0)
    bootstrap_replicates_used: int = Field(default=0, ge=0, le=MAX_BOOTSTRAPS)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def statistics_match_state(self) -> Self:
        statistics = (
            self.measurement_standard_error,
            self.fitted_model_standard_error,
            self.measurement_model_covariance,
            self.combined_standard_error,
            self.variance_closure_residual,
        )
        if self.state is UncertaintyState.ESTIMATED:
            if any(value is None for value in statistics) or self.bootstrap_replicates_used == 0:
                raise ValueError(
                    "estimated uncertainty requires all components and bootstrap replicates"
                )
            if self.reason is not None:
                raise ValueError("estimated uncertainty cannot carry a reason")
        else:
            if any(value is not None for value in statistics):
                raise ValueError("non-estimable uncertainty cannot carry statistics")
            if self.bootstrap_replicates_used != 0 or self.reason is None:
                raise ValueError("non-estimable uncertainty requires a reason and zero bootstraps")
        return self


class ComplexMemberContribution(FrozenModel):
    gene_symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9._/-]*$")
    from_observation_id: Identifier
    to_observation_id: Identifier
    from_provenance_digest: Sha256Digest
    to_provenance_digest: Sha256Digest
    value_semantics: Literal[ValueSemantics.EXACT_DELTA]
    standardized_delta: float
    member_loading: float
    reliability_weight: float = Field(gt=0.0, le=1.0)
    contribution: float
    direction: ContributionDirection

    @model_validator(mode="after")
    def direction_matches_contribution(self) -> Self:
        if self.contribution == 0.0:
            raise ValueError("zero complex-member contributions are not ranked")
        expected = (
            ContributionDirection.SOURCE_RECURRENCE_ALIGNED
            if self.contribution > 0.0
            else ContributionDirection.SOURCE_PRIMARY_ALIGNED
        )
        if self.direction is not expected:
            raise ValueError("complex-member contribution direction does not match its sign")
        return self


class ComplexComponentAblation(FrozenModel):
    component_kind: Literal[
        "source_processing",
        "uniform_member_loading",
        "top_member",
        "nested_family",
    ]
    component_id: NonEmptyStr
    support: AnalysisSupport
    score_without_component: float | None = None
    score_delta: float | None = None
    classification_without_component: ComplexTransitionClassification
    removed_member_count: int = Field(ge=0, le=MAX_MEMBERS_PER_COMPLEX)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def estimate_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if self.score_without_component is not None or self.score_delta is not None:
                raise ValueError("abstained ablations cannot carry estimates")
            if (
                self.classification_without_component
                is not ComplexTransitionClassification.NOT_ESTIMABLE
            ):
                raise ValueError("abstained ablations must be not_estimable")
            if self.reason is None:
                raise ValueError("abstained ablations require a reason")
        else:
            if self.score_without_component is None or self.score_delta is None:
                raise ValueError("estimated ablations require score and delta")
            if (
                self.classification_without_component
                is ComplexTransitionClassification.NOT_ESTIMABLE
            ):
                raise ValueError("estimated ablations cannot be not_estimable")
            if self.support is AnalysisSupport.SUPPORTED and self.reason is not None:
                raise ValueError("supported ablations cannot carry a reason")
            if self.support is AnalysisSupport.LIMITED and self.reason is None:
                raise ValueError("limited ablations require a reason")
        return self


class ComplexTransitionAblations(FrozenModel):
    source_processing: ComplexComponentAblation | None = None
    uniform_member_loading: ComplexComponentAblation | None = None
    top_member: ComplexComponentAblation | None = None
    nested_family: ComplexComponentAblation | None = None

    def has_any(self) -> bool:
        return any(
            item is not None
            for item in (
                self.source_processing,
                self.uniform_member_loading,
                self.top_member,
                self.nested_family,
            )
        )


def classify_interval(lower: float, upper: float) -> ComplexTransitionClassification:
    if lower > 0.25:
        return ComplexTransitionClassification.SOURCE_RECURRENCE_ALIGNED
    if upper < -0.25:
        return ComplexTransitionClassification.SOURCE_PRIMARY_ALIGNED
    if lower >= -0.25 and upper <= 0.25:
        return ComplexTransitionClassification.STABLE
    return ComplexTransitionClassification.INDETERMINATE


class ComplexMemberTransitionConcordance(FrozenModel):
    complex_index: int = Field(ge=0, lt=MAX_COMPLEXES)
    domain_id: Identifier
    reactome_id: str = Field(pattern=r"^R-HSA-[1-9][0-9]*$")
    complex_name: NonEmptyStr
    family_id: Identifier
    output_semantics: Literal["source_cohort_complex_member_transition_concordance"] = (
        "source_cohort_complex_member_transition_concordance"
    )
    support: AnalysisSupport
    classification: ComplexTransitionClassification
    score: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    interval_level: float = Field(default=0.9, ge=0.9, le=0.9)
    active_member_count: int = Field(ge=0, le=MAX_MEMBERS_PER_COMPLEX)
    observed_member_count: int = Field(ge=0, le=MAX_MEMBERS_PER_COMPLEX)
    left_censored_member_count: int = Field(ge=0, le=MAX_MEMBERS_PER_COMPLEX)
    coefficient_mass_coverage: float = Field(ge=0.0, le=1.0)
    effective_sample_size: float = Field(ge=0.0)
    coherence: float | None = Field(default=None, ge=0.0, le=1.0)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    solver_converged: bool | None = None
    solver_iterations: int | None = Field(default=None, ge=1, le=200)
    solver_initial_objective: float | None = Field(default=None, ge=0.0)
    solver_final_objective: float | None = Field(default=None, ge=0.0)
    solver_objective_monotone: bool | None = None
    bootstrap_failed_replicates: int = Field(default=0, ge=0, le=MAX_BOOTSTRAPS)
    least_source_aligned_observed_member: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Z0-9][A-Z0-9._/-]*$",
    )
    source_held_member_relative_gain: float
    source_panel_patient_cluster_gain_90_interval: tuple[float, float]
    source_direction_accuracy: float = Field(ge=0.0, le=1.0)
    source_minimum_outer_loading_cosine: float = Field(ge=-1.0, le=1.0)
    uncertainty: ComplexTransitionUncertainty
    top_contributions: tuple[ComplexMemberContribution, ...] = Field(
        default=(),
        max_length=MAX_TOP_CONTRIBUTIONS,
    )
    ablations: ComplexTransitionAblations
    limitations: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def evidence_is_coherent_with_support(self) -> Self:
        if self.observed_member_count + self.left_censored_member_count != self.active_member_count:
            raise ValueError("active complex-member counts do not close")
        interval_lower, interval_upper = self.source_panel_patient_cluster_gain_90_interval
        if interval_lower > interval_upper:
            raise ValueError("source held-member gain interval is reversed")
        estimate = (self.score, self.lower_bound, self.upper_bound)
        if self.support is AnalysisSupport.ABSTAINED:
            if any(value is not None for value in estimate):
                raise ValueError("abstained complex concordance cannot carry estimates")
            if self.classification is not ComplexTransitionClassification.NOT_ESTIMABLE:
                raise ValueError("abstained complex concordance must be not_estimable")
            if any(
                value is not None
                for value in (
                    self.coherence,
                    self.discordance,
                    self.stability,
                    self.least_source_aligned_observed_member,
                    self.solver_converged,
                    self.solver_iterations,
                    self.solver_initial_objective,
                    self.solver_final_objective,
                    self.solver_objective_monotone,
                )
            ):
                raise ValueError("abstained complex concordance cannot carry diagnostics")
            if self.uncertainty.state is not UncertaintyState.NOT_ESTIMABLE:
                raise ValueError("abstained complex uncertainty must be non-estimable")
            if self.top_contributions or self.ablations.has_any() or not self.limitations:
                raise ValueError("abstained complex concordance requires reasons only")
            if self.bootstrap_failed_replicates != 0:
                raise ValueError("abstained complex concordance cannot carry bootstrap failures")
            return self

        if any(value is None for value in estimate):
            raise ValueError("estimated complex concordance requires score and interval")
        score = cast("float", self.score)
        lower = cast("float", self.lower_bound)
        upper = cast("float", self.upper_bound)
        if not lower <= score <= upper:
            raise ValueError("complex concordance interval must contain the score")
        if self.classification is not classify_interval(lower, upper):
            raise ValueError("complex classification must be supported by its interval")
        if (
            self.active_member_count < MIN_ACTIVE_MEMBERS
            or self.coefficient_mass_coverage < MIN_COEFFICIENT_MASS
            or self.effective_sample_size < MIN_EFFECTIVE_SAMPLE_SIZE
        ):
            raise ValueError("estimated complex concordance does not meet support gates")
        if (
            self.coherence is None
            or self.discordance is None
            or self.stability is None
            or abs(self.coherence + self.discordance - 1.0) > 1e-7
            or self.uncertainty.state is not UncertaintyState.ESTIMATED
            or self.ablations.source_processing is None
            or self.ablations.uniform_member_loading is None
            or self.solver_converged is not True
            or self.solver_iterations is None
            or self.solver_initial_objective is None
            or self.solver_final_objective is None
            or self.solver_objective_monotone is not True
        ):
            raise ValueError(
                "estimated complex concordance requires coherent diagnostics and ablations"
            )
        if self.observed_member_count > 0 and self.least_source_aligned_observed_member is None:
            raise ValueError("observed complex evidence requires a least-aligned member")
        if self.support is AnalysisSupport.LIMITED and not self.limitations:
            raise ValueError("limited complex concordance requires a limitation")
        if self.support is AnalysisSupport.SUPPORTED:
            if self.limitations:
                raise ValueError("supported complex concordance cannot carry limitations")
            if (
                self.classification
                in {
                    ComplexTransitionClassification.INDETERMINATE,
                    ComplexTransitionClassification.NOT_ESTIMABLE,
                }
                or self.stability < SUPPORTED_MIN_STABILITY
                or self.source_minimum_outer_loading_cosine < SUPPORTED_MIN_LOADING_COSINE
                or self.source_held_member_relative_gain <= 0.0
                or interval_lower <= 0.0
            ):
                raise ValueError(
                    "supported complex concordance requires stable positive held-member evidence"
                )
        return self


class ComplexTransitionEvidence(FrozenModel):
    transition_id: Identifier
    transition_index: int = Field(ge=0, lt=MAX_TIME_POINTS - 1)
    from_time_point_id: Identifier
    to_time_point_id: Identifier
    duration_days: float = Field(gt=0.0)
    complexes: tuple[ComplexMemberTransitionConcordance, ...] = Field(
        min_length=1,
        max_length=MAX_COMPLEXES,
    )

    @model_validator(mode="after")
    def complex_panel_is_ordered_and_unique(self) -> Self:
        indices = tuple(item.complex_index for item in self.complexes)
        reactome_ids = tuple(item.reactome_id for item in self.complexes)
        if indices != tuple(range(len(indices))):
            raise ValueError("complex results must preserve contiguous source-panel order")
        if len(reactome_ids) != len(set(reactome_ids)):
            raise ValueError("complex results must have unique Reactome identifiers")
        return self


class ComplexTransitionProvenance(FrozenModel):
    source_study_id: Literal["PDC000514"]
    source_patient_pair_count: Literal[104]
    reactome_release: Literal[97]
    source_catalog_digest: Sha256Digest
    fitted_model_digest: Sha256Digest
    training_recipe_digest: Sha256Digest
    panel_selection_digest: Sha256Digest
    participant_membership_digest: Sha256Digest
    source_licenses: tuple[NonEmptyStr, ...] = Field(min_length=2, max_length=4)
    source_attribution: NonEmptyStr
    validation_scope: Literal["internal_patient_grouped_held_member_reconstruction"]
    patient_level_data_packaged: Literal[False] = False
    external_validation_performed: Literal[False] = False


class _ComplexTransitionResultDocument(FrozenModel):
    profile_id: Literal["kncc-reactome-complex-transition/1.0.0"] = (
        "kncc-reactome-complex-transition/1.0.0"
    )
    model_id: Literal["kncc-reactome-complex-transition-factor-model/1.0.0"] = (
        "kncc-reactome-complex-transition-factor-model/1.0.0"
    )
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    profile_digest: Sha256Digest
    source_catalog_digest: Sha256Digest
    fitted_model_digest: Sha256Digest
    computational_seed: int = Field(ge=0, le=2**53 - 1)
    series_id: Identifier
    assay_compatibility: AssayCompatibilityAttestation
    normalization_reference: NormalizationReference
    time_point_ids: tuple[Identifier, ...] = Field(
        min_length=MIN_TIME_POINTS,
        max_length=MAX_TIME_POINTS,
    )
    transitions: tuple[ComplexTransitionEvidence, ...] = Field(
        min_length=1,
        max_length=MAX_TIME_POINTS - 1,
    )
    output_semantics: Literal["reactome_participant_set_transition_concordance"] = (
        "reactome_participant_set_transition_concordance"
    )
    provenance: ComplexTransitionProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=24)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    infers_complex_assembly: Literal[False] = False
    infers_complex_activity: Literal[False] = False
    infers_stoichiometry: Literal[False] = False
    infers_essential_subunits: Literal[False] = False
    infers_causality: Literal[False] = False

    @model_validator(mode="after")
    def transition_topology_matches_time_points(self) -> Self:
        if len(self.transitions) != len(self.time_point_ids) - 1:
            raise ValueError("result must contain one transition per adjacent time-point pair")
        for index, transition in enumerate(self.transitions):
            if (
                transition.transition_index != index
                or transition.from_time_point_id != self.time_point_ids[index]
                or transition.to_time_point_id != self.time_point_ids[index + 1]
            ):
                raise ValueError("result transition topology does not match time-point order")
        return self


class LongitudinalGbmComplexTransitionResult(_ComplexTransitionResultDocument):
    @model_validator(mode="after")
    def result_digest_is_content_bound(self) -> Self:
        if result_payload_digest(self) != self.result_digest:
            raise ValueError("complex-transition result digest mismatch")
        return self


class UnverifiedLongitudinalGbmComplexTransitionResult(_ComplexTransitionResultDocument):
    """Structural result used only to calculate or check the self digest."""


class ComplexTransitionReplayVerificationRequest(FrozenModel):
    request: LongitudinalGbmComplexTransitionRequest
    result: (
        LongitudinalGbmComplexTransitionResult | UnverifiedLongitudinalGbmComplexTransitionResult
    )


class ComplexTransitionReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    transition_topology_match: bool
    complex_semantic_match: bool
    uncertainty_semantic_match: bool
    ablation_semantic_match: bool
    provenance_match: bool
    document_semantic_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    authoritative_profile_digest: Sha256Digest
    message: NonEmptyStr

    @model_validator(mode="after")
    def verified_is_conjunction(self) -> Self:
        expected_semantic = all(
            (
                self.transition_topology_match,
                self.complex_semantic_match,
                self.uncertainty_semantic_match,
                self.ablation_semantic_match,
                self.provenance_match,
                self.document_semantic_match,
            )
        )
        if self.semantic_match is not expected_semantic:
            raise ValueError("semantic replay flag does not close its checks")
        expected = all(
            (
                self.request_digest_match,
                self.profile_digest_match,
                self.result_digest_match,
                self.semantic_match,
            )
        )
        if self.verified is not expected:
            raise ValueError("verified replay flag does not close its checks")
        return self


class ComplexTransitionAlgorithmConstants(FrozenModel):
    huber_k: float = Field(default=1.345, ge=1.345, le=1.345)
    ridge_lambda: float = Field(default=0.075, ge=0.075, le=0.075)
    damping: float = Field(default=0.7, ge=0.7, le=0.7)
    maximum_iterations: Literal[200] = 200
    tolerance: float = Field(default=1e-9, ge=1e-9, le=1e-9)
    objective_increase_tolerance: float = Field(default=1e-10, ge=1e-10, le=1e-10)
    quantization_decimals: Literal[10] = 10
    interval_level: float = Field(default=0.9, ge=0.9, le=0.9)
    minimum_active_members: Literal[3] = 3
    minimum_member_reliability: float = Field(default=0.05, ge=0.05, le=0.05)
    minimum_coefficient_mass: float = Field(default=0.5, ge=0.5, le=0.5)
    minimum_effective_sample_size: float = Field(default=2.0, ge=2.0, le=2.0)
    classification_threshold: float = Field(default=0.25, ge=0.25, le=0.25)
    supported_minimum_stability: float = Field(default=0.8, ge=0.8, le=0.8)
    supported_minimum_loading_cosine: float = Field(default=0.8, ge=0.8, le=0.8)
    bootstrap_generator: Literal["numpy.random.Generator(PCG64)"] = "numpy.random.Generator(PCG64)"


class ComplexTransitionLimits(FrozenModel):
    minimum_time_points: Literal[2] = 2
    maximum_time_points: Literal[16] = 16
    maximum_observations_per_time_point: Literal[4096] = 4096
    maximum_total_observations: Literal[12000] = 12000
    minimum_bootstrap_replicates: Literal[32] = 32
    default_bootstrap_replicates: Literal[64] = 64
    maximum_bootstrap_replicates: Literal[256] = 256
    maximum_complexes: Literal[64] = 64
    maximum_members_per_complex: Literal[32] = 32
    maximum_request_bytes: Literal[2097152] = 2_097_152
    maximum_result_bytes: Literal[4194304] = 4_194_304
    maximum_replay_bytes: Literal[8388608] = 8_388_608


class ComplexProfileItem(FrozenModel):
    complex_index: int = Field(ge=0, lt=MAX_COMPLEXES)
    domain_id: Identifier
    reactome_id: str = Field(pattern=r"^R-HSA-[1-9][0-9]*$")
    complex_name: NonEmptyStr
    family_id: Identifier
    selection_tier: NonEmptyStr
    mapped_member_count: int = Field(ge=3, le=MAX_MEMBERS_PER_COMPLEX)
    fitted_member_count: int = Field(ge=3, le=MAX_MEMBERS_PER_COMPLEX)
    source_held_member_relative_gain: float
    source_panel_patient_cluster_gain_90_interval: tuple[float, float]
    source_direction_accuracy: float = Field(ge=0.0, le=1.0)
    minimum_outer_loading_cosine: float = Field(ge=-1.0, le=1.0)


class ComplexTransitionSourceCounts(FrozenModel):
    source_gene_count: int = Field(ge=1)
    eligible_source_gene_count: int = Field(ge=1)
    strict_patient_pair_count: Literal[104] = 104
    complex_count: int = Field(ge=1, le=MAX_COMPLEXES)
    total_member_count: int = Field(ge=3)
    unique_member_gene_count: int = Field(ge=3)
    nested_family_count: int = Field(ge=1, le=MAX_COMPLEXES)
    outer_fold_count: Literal[8] = 8
    fitted_bootstrap_replicate_count: int = Field(ge=128, le=512)


class ComplexTransitionSourceDigests(FrozenModel):
    source_catalog_artifact_digest: Sha256Digest
    source_catalog_content_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    panel_selection_digest: Sha256Digest
    participant_membership_digest: Sha256Digest
    overlap_control_digest: Sha256Digest
    gene_order_digest: Sha256Digest
    fitted_artifact_digest: Sha256Digest
    fitted_content_digest: Sha256Digest
    reference_loading_digest: Sha256Digest
    bootstrap_ensemble_digest: Sha256Digest
    bootstrap_seed_namespace_digest: Sha256Digest
    training_recipe_digest: Sha256Digest
    fold_policy_digest: Sha256Digest
    source_processing_ablation_digest: Sha256Digest
    evaluation_digest: Sha256Digest
    demo_request_digest: Sha256Digest
    input_contract_schema_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest


class ComplexTransitionEvaluationSummary(FrozenModel):
    validation_scope: Literal["internal_patient_grouped_held_member_reconstruction"]
    patient_count: Literal[104]
    evaluation_count: int = Field(ge=1)
    zero_transition_mean_standardized_mae: float = Field(ge=0.0)
    training_center_mean_standardized_mae: float = Field(ge=0.0)
    factor_model_mean_standardized_mae: float = Field(ge=0.0)
    mean_relative_gain_over_training_center: float
    patient_cluster_median_gain_90_interval: tuple[float, float]
    held_member_direction_accuracy: float = Field(ge=0.0, le=1.0)
    minimum_outer_loading_cosine: float = Field(ge=-1.0, le=1.0)
    nonconverged_reference_fit_count: int = Field(ge=0)
    nonconverged_outer_fit_count: int = Field(ge=0)
    external_validation_performed: Literal[False] = False


class LongitudinalGbmComplexTransitionProfile(FrozenModel):
    algorithm_id: Literal["kncc-reactome-complex-transition"] = "kncc-reactome-complex-transition"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-reactome-complex-transition/1.0.0"] = (
        "kncc-reactome-complex-transition/1.0.0"
    )
    model_id: Literal["kncc-reactome-complex-transition-factor-model/1.0.0"] = (
        "kncc-reactome-complex-transition-factor-model/1.0.0"
    )
    profile_digest: Sha256Digest
    required_assay_compatibility: AssayCompatibilityAttestation
    numpy_version: Literal["2.5.2"]
    constants: ComplexTransitionAlgorithmConstants
    limits: ComplexTransitionLimits
    counts: ComplexTransitionSourceCounts
    digests: ComplexTransitionSourceDigests
    evaluation: ComplexTransitionEvaluationSummary
    complexes: tuple[ComplexProfileItem, ...] = Field(
        min_length=1,
        max_length=MAX_COMPLEXES,
    )
    source_licenses: tuple[NonEmptyStr, ...] = Field(min_length=2, max_length=4)
    source_attribution: NonEmptyStr
    claim_ceiling: Literal["source_cohort_reactome_participant_set_transition_concordance_only"]
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=24)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def profile_is_ordered_and_content_bound(self) -> Self:
        indices = tuple(item.complex_index for item in self.complexes)
        if indices != tuple(range(len(indices))):
            raise ValueError("profile complex panel must preserve contiguous source order")
        if self.counts.complex_count != len(self.complexes):
            raise ValueError("profile complex count does not match its panel")
        if profile_payload_digest(self) != self.profile_digest:
            raise ValueError("complex-transition profile digest mismatch")
        return self


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "DEFAULT_BOOTSTRAPS",
    "MAX_BOOTSTRAPS",
    "MAX_COMPLEXES",
    "MAX_MEMBERS_PER_COMPLEX",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "MODEL_ID",
    "PROFILE_ID",
    "REQUIRED_ASSAY_COMPATIBILITY",
    "AnalysisSupport",
    "AssayCompatibilityAttestation",
    "ComplexComponentAblation",
    "ComplexMemberContribution",
    "ComplexMemberTransitionConcordance",
    "ComplexProfileItem",
    "ComplexTransitionAblations",
    "ComplexTransitionAlgorithmConstants",
    "ComplexTransitionClassification",
    "ComplexTransitionEvaluationSummary",
    "ComplexTransitionEvidence",
    "ComplexTransitionLimits",
    "ComplexTransitionProvenance",
    "ComplexTransitionReplayVerificationRequest",
    "ComplexTransitionReplayVerificationResult",
    "ComplexTransitionSourceCounts",
    "ComplexTransitionSourceDigests",
    "ComplexTransitionUncertainty",
    "ContributionDirection",
    "LongitudinalGbmComplexTransitionProfile",
    "LongitudinalGbmComplexTransitionRequest",
    "LongitudinalGbmComplexTransitionResult",
    "LongitudinalTimePoint",
    "NormalizationReference",
    "ProteinEvidenceState",
    "ProteinObservation",
    "UncertaintyState",
    "UnverifiedLongitudinalGbmComplexTransitionResult",
    "ValueSemantics",
    "classify_interval",
]
