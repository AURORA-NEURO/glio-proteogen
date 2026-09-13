"""Strict public contracts for fitted KNCC/Neftel program transitions.

The lane estimates one global paired bulk-protein transition coordinate and
eight Neftel-program coordinates conditional on it.  Outputs are same-cohort
concordance only: never recurrence prediction, patient evolution, subtype,
deconvolution, activation, causal biology, prognosis, or treatment guidance.
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

from .canonical import (
    canonical_request_digest,
    profile_payload_digest,
    result_payload_digest,
    sha256_digest,
)
from .catalog import EXPECTED_PROGRAMS

ALGORITHM_ID = "kncc-neftel-program-transition"
ALGORITHM_VERSION = "1.0.0"
ALGORITHM_PROFILE_ID = "kncc-neftel-program-transition/1.0.0"
PROFILE_ID = ALGORITHM_PROFILE_ID
MODEL_ID = "kncc-neftel-program-transition-model/1.0.0"

MIN_TIME_POINTS = 2
MAX_TIME_POINTS = 16
MAX_OBSERVATIONS_PER_TIME_POINT = 4_096
MAX_TOTAL_OBSERVATIONS = 12_000
MIN_BOOTSTRAPS = 32
DEFAULT_BOOTSTRAPS = 64
MAX_BOOTSTRAPS = 256
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 4 * 1_024 * 1_024
MAX_REPLAY_BYTES = 8 * 1_024 * 1_024
MAX_TOP_CONTRIBUTIONS = 10
MAX_OVERLAP_ABLATIONS = 9
PROGRAM_COUNT = 8
SOLVER_FIXED_WORK_UNITS_PER_TRANSITION = 186
SOLVER_BOOTSTRAP_WORK_UNITS_PER_REPLICATE = 3
MAX_SOLVER_WORK_UNITS = 4_608

GLOBAL_MIN_ACTIVE_GENES = 16
GLOBAL_MIN_EXACT_GENES = 16
GLOBAL_MIN_COEFFICIENT_MASS = 0.25
GLOBAL_MIN_EFFECTIVE_SAMPLE_SIZE = 8.0
PROGRAM_MIN_ACTIVE_GENES = 5
PROGRAM_MIN_EXACT_GENES = 5
PROGRAM_MIN_COEFFICIENT_MASS = 0.50
PROGRAM_MIN_EFFECTIVE_SAMPLE_SIZE = 3.0
PROGRAM_MIN_UNIQUE_GENES = 3
PROGRAM_MIN_UNIQUE_MASS = 0.20


class AnalysisSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class GlobalTransitionClassification(StrEnum):
    SOURCE_LATER_TIMEPOINT_ALIGNED = "source_later_timepoint_aligned"
    SOURCE_EARLIER_TIMEPOINT_ALIGNED = "source_earlier_timepoint_aligned"
    STABLE = "stable"
    INDETERMINATE = "indeterminate"
    NOT_ESTIMABLE = "not_estimable"


class ConditionalTransitionClassification(StrEnum):
    CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED = "conditional_source_later_timepoint_aligned"
    CONDITIONAL_SOURCE_EARLIER_TIMEPOINT_ALIGNED = "conditional_source_earlier_timepoint_aligned"
    CONDITIONALLY_STABLE = "conditionally_stable"
    INDETERMINATE = "indeterminate"
    NOT_ESTIMABLE = "not_estimable"


class UncertaintyState(StrEnum):
    ESTIMATED = "estimated"
    NOT_ESTIMABLE = "not_estimable"


class ContributionDirection(StrEnum):
    CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED = "conditional_source_later_timepoint_aligned"
    CONDITIONAL_SOURCE_EARLIER_TIMEPOINT_ALIGNED = "conditional_source_earlier_timepoint_aligned"


class ValueSemantics(StrEnum):
    EXACT_DELTA = "exact_delta"
    UPPER_BOUND = "upper_bound"
    LOWER_BOUND = "lower_bound"


class LongitudinalGbmNeftelTransitionRequest(FrozenModel):
    """One caller-owned, ordered protein series on the locked KNCC assay scale."""

    profile_id: Literal["kncc-neftel-program-transition/1.0.0"] = (
        "kncc-neftel-program-transition/1.0.0"
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
        time_point_ids = tuple(point.time_point_id for point in self.time_points)
        if len(time_point_ids) != len(set(time_point_ids)):
            raise ValueError("longitudinal time-point identifiers must be unique")
        offsets = tuple(point.time_offset_days for point in self.time_points)
        if any(current >= following for current, following in pairwise(offsets)):
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
                f"Neftel transition requests are limited to {MAX_TOTAL_OBSERVATIONS} observations"
            )
        work_units = (len(self.time_points) - 1) * (
            SOLVER_FIXED_WORK_UNITS_PER_TRANSITION
            + SOLVER_BOOTSTRAP_WORK_UNITS_PER_REPLICATE * self.bootstrap_replicates
        )
        if work_units > MAX_SOLVER_WORK_UNITS:
            raise ValueError(
                "Neftel transition request exceeds the 4608 solver-work-unit limit: "
                "(time_points - 1) * (186 + 3 * bootstrap_replicates)"
            )
        return self

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class ConditionalUncertaintyDecomposition(FrozenModel):
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
                    "estimated uncertainty requires every component and bootstrap replicates"
                )
            if self.reason is not None:
                raise ValueError("estimated uncertainty cannot carry a reason")
        else:
            if any(value is not None for value in statistics):
                raise ValueError("non-estimable uncertainty cannot carry statistics")
            if self.bootstrap_replicates_used != 0 or self.reason is None:
                raise ValueError(
                    "non-estimable uncertainty requires a reason and zero bootstrap replicates"
                )
        return self


class ConditionalProteinContribution(FrozenModel):
    """Observed-gene evidence decomposition, not an additive joint-score decomposition."""

    gene_symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9._/-]*$")
    from_observation_id: Identifier
    to_observation_id: Identifier
    from_provenance_digest: Sha256Digest
    to_provenance_digest: Sha256Digest
    from_state: Literal[ProteinEvidenceState.OBSERVED]
    to_state: Literal[ProteinEvidenceState.OBSERVED]
    value_semantics: Literal[ValueSemantics.EXACT_DELTA]
    standardized_delta: float
    program_loading: float
    global_loading: float
    unadjusted_contribution: float
    global_adjustment_contribution: float
    conditional_contribution: float
    direction: ContributionDirection
    reliability_weight: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def direction_and_decomposition_are_consistent(self) -> Self:
        expected = self.unadjusted_contribution - self.global_adjustment_contribution
        if abs(self.conditional_contribution - expected) > 1e-7:
            raise ValueError("conditional contribution does not close its decomposition")
        if self.conditional_contribution == 0.0:
            raise ValueError("zero contributions must not appear in the ranked explanation")
        expected_direction = (
            ContributionDirection.CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED
            if self.conditional_contribution > 0.0
            else ContributionDirection.CONDITIONAL_SOURCE_EARLIER_TIMEPOINT_ALIGNED
        )
        if self.direction is not expected_direction:
            raise ValueError("contribution direction does not match its sign")
        return self


class ConditionalComponentAblation(FrozenModel):
    component_kind: Literal[
        "global_axis",
        "source_processing",
        "degree_normalization",
        "unique_members",
        "leave_program_out",
        "overlapping_program",
        "top_contribution",
    ]
    component_id: NonEmptyStr
    support: AnalysisSupport
    conditional_score_without_component: float | None = None
    score_delta: float | None = None
    classification_without_component: ConditionalTransitionClassification
    removed_feature_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def estimate_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if self.conditional_score_without_component is not None or self.score_delta is not None:
                raise ValueError("abstained ablations cannot carry numeric estimates")
            if (
                self.classification_without_component
                is not ConditionalTransitionClassification.NOT_ESTIMABLE
            ):
                raise ValueError("abstained ablations must be not_estimable")
            if self.reason is None:
                raise ValueError("abstained ablations require a reason")
        else:
            if self.conditional_score_without_component is None or self.score_delta is None:
                raise ValueError("estimated ablations require score and score delta")
            if (
                self.classification_without_component
                is ConditionalTransitionClassification.NOT_ESTIMABLE
            ):
                raise ValueError("estimated ablations cannot be not_estimable")
            if self.support is AnalysisSupport.SUPPORTED and self.reason is not None:
                raise ValueError("supported ablations cannot carry a limitation reason")
            if self.support is AnalysisSupport.LIMITED and self.reason is None:
                raise ValueError("limited ablations require a limitation reason")
        return self


class ConditionalProgramAblations(FrozenModel):
    global_axis: ConditionalComponentAblation | None = None
    source_processing: tuple[ConditionalComponentAblation, ...] = Field(
        default=(),
        max_length=4,
    )
    degree_normalization: ConditionalComponentAblation | None = None
    unique_members: ConditionalComponentAblation | None = None
    leave_program_out: ConditionalComponentAblation | None = None
    overlap: tuple[ConditionalComponentAblation, ...] = Field(
        default=(),
        max_length=MAX_OVERLAP_ABLATIONS,
    )
    top_contributions: tuple[ConditionalComponentAblation, ...] = Field(
        default=(),
        max_length=MAX_TOP_CONTRIBUTIONS,
    )

    def has_any(self) -> bool:
        return any(
            (
                self.global_axis is not None,
                bool(self.source_processing),
                self.degree_normalization is not None,
                self.unique_members is not None,
                self.leave_program_out is not None,
                bool(self.overlap),
                bool(self.top_contributions),
            )
        )

    def required_structural(
        self,
    ) -> tuple[ConditionalComponentAblation, ...] | None:
        if (
            not self.source_processing
            or self.degree_normalization is None
            or self.unique_members is None
        ):
            return None
        return (
            *self.source_processing,
            self.degree_normalization,
            self.unique_members,
        )


def _expected_global_classification(
    lower: float,
    upper: float,
) -> GlobalTransitionClassification:
    if lower > 0.25:
        return GlobalTransitionClassification.SOURCE_LATER_TIMEPOINT_ALIGNED
    if upper < -0.25:
        return GlobalTransitionClassification.SOURCE_EARLIER_TIMEPOINT_ALIGNED
    if lower >= -0.25 and upper <= 0.25:
        return GlobalTransitionClassification.STABLE
    return GlobalTransitionClassification.INDETERMINATE


def _expected_program_classification(
    lower: float,
    upper: float,
) -> ConditionalTransitionClassification:
    if lower > 0.25:
        return ConditionalTransitionClassification.CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED
    if upper < -0.25:
        return ConditionalTransitionClassification.CONDITIONAL_SOURCE_EARLIER_TIMEPOINT_ALIGNED
    if lower >= -0.25 and upper <= 0.25:
        return ConditionalTransitionClassification.CONDITIONALLY_STABLE
    return ConditionalTransitionClassification.INDETERMINATE


class GlobalTransitionConcordance(FrozenModel):
    output_semantics: Literal["global_transition_concordance"] = "global_transition_concordance"
    support: AnalysisSupport
    classification: GlobalTransitionClassification
    score: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    interval_level: float = Field(default=0.9, ge=0.9, le=0.9)
    admitted_active_gene_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    shared_active_gene_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    observed_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    left_censored_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    admitted_left_censored_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    coefficient_mass_coverage: float = Field(ge=0.0, le=1.0)
    effective_sample_size: float = Field(ge=0.0)
    bootstrap_replicates_used: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    abstention_reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def interpretation_matches_support(self) -> Self:
        if self.shared_active_gene_count != self.observed_count + self.left_censored_count:
            raise ValueError("informative global count must equal exact plus binding-censor counts")
        if self.admitted_active_gene_count != (
            self.observed_count + self.admitted_left_censored_count
        ):
            raise ValueError("admitted global count must equal exact plus admitted-censor counts")
        if (
            self.admitted_active_gene_count < self.shared_active_gene_count
            or self.admitted_left_censored_count < self.left_censored_count
        ):
            raise ValueError("informative global evidence cannot exceed admitted evidence")
        estimate = (self.score, self.lower_bound, self.upper_bound)
        if self.support is AnalysisSupport.ABSTAINED:
            if any(value is not None for value in estimate):
                raise ValueError("abstained global concordance cannot carry estimates")
            if self.classification is not GlobalTransitionClassification.NOT_ESTIMABLE:
                raise ValueError("abstained global concordance must be not_estimable")
            if self.bootstrap_replicates_used != 0 or not self.abstention_reasons:
                raise ValueError(
                    "abstained global concordance requires reasons and zero bootstraps"
                )
        else:
            if self.support is AnalysisSupport.SUPPORTED:
                raise ValueError(
                    "global transition concordance is capped at limited because the "
                    "locked evidence is same-cohort without external validation"
                )
            if any(value is None for value in estimate):
                raise ValueError("estimated global concordance requires a complete interval")
            score = cast("float", self.score)
            lower = cast("float", self.lower_bound)
            upper = cast("float", self.upper_bound)
            if not lower <= score <= upper:
                raise ValueError("global concordance interval must contain its score")
            if self.classification is not _expected_global_classification(lower, upper):
                raise ValueError("global classification must be supported by its interval")
            if (
                self.shared_active_gene_count < GLOBAL_MIN_ACTIVE_GENES
                or self.observed_count < GLOBAL_MIN_EXACT_GENES
                or self.coefficient_mass_coverage < GLOBAL_MIN_COEFFICIENT_MASS
                or self.effective_sample_size < GLOBAL_MIN_EFFECTIVE_SAMPLE_SIZE
            ):
                raise ValueError("estimated global concordance does not meet support gates")
            if self.bootstrap_replicates_used == 0:
                raise ValueError("estimated global concordance requires bootstraps")
            if self.support is AnalysisSupport.LIMITED and not self.abstention_reasons:
                raise ValueError("limited global concordance requires a limitation reason")
        return self


def _validate_abstained_program(
    program: NeftelProgramConcordance,
    estimate: tuple[float | None, ...],
) -> None:
    if any(value is not None for value in estimate):
        raise ValueError("abstained program concordance cannot carry estimates")
    if program.classification is not ConditionalTransitionClassification.NOT_ESTIMABLE:
        raise ValueError("abstained program concordance must be not_estimable")
    if any(
        value is not None
        for value in (
            program.stability,
            program.discordance,
        )
    ):
        raise ValueError("abstained program concordance cannot carry diagnostics")
    if program.uncertainty.state is not UncertaintyState.NOT_ESTIMABLE:
        raise ValueError("abstained program uncertainty must be non-estimable")
    if (
        program.request_reconstruction_evaluable_fold_count != 0
        or program.request_reconstruction_improved_fold_count != 0
        or program.request_reconstruction_median_relative_gain is not None
    ):
        raise ValueError("abstained program cannot carry request reconstruction evidence")
    if program.top_contributions or program.ablations.has_any():
        raise ValueError("abstained program concordance cannot carry explanations")
    if not program.abstention_reasons:
        raise ValueError("abstained program concordance requires a reason")


def _validate_estimated_program(
    program: NeftelProgramConcordance,
    estimate: tuple[float | None, ...],
    structural: tuple[ConditionalComponentAblation, ...] | None,
) -> None:
    if any(value is None for value in estimate):
        raise ValueError("estimated program concordance requires every coordinate")
    score = cast("float", program.score)
    lower = cast("float", program.lower_bound)
    upper = cast("float", program.upper_bound)
    if not lower <= score <= upper:
        raise ValueError("program concordance interval must contain its score")
    if program.classification is not _expected_program_classification(lower, upper):
        raise ValueError("program classification must be supported by its interval")
    if (
        program.active_feature_count < PROGRAM_MIN_ACTIVE_GENES
        or program.observed_count < PROGRAM_MIN_EXACT_GENES
        or program.coefficient_mass_coverage < PROGRAM_MIN_COEFFICIENT_MASS
        or program.effective_sample_size < PROGRAM_MIN_EFFECTIVE_SAMPLE_SIZE
    ):
        raise ValueError("estimated program concordance does not meet support gates")
    if (
        program.stability is None
        or program.discordance is None
        or program.uncertainty.state is not UncertaintyState.ESTIMATED
        or program.ablations.global_axis is None
        or structural is None
        or program.ablations.leave_program_out is None
        or program.request_reconstruction_median_relative_gain is None
    ):
        raise ValueError("estimated program concordance requires uncertainty and explanations")
    if program.support is AnalysisSupport.SUPPORTED:
        raise ValueError(
            "fitted program concordance cannot be supported because the locked "
            "dictionary was not preferred to the equal-membership baseline"
        )
    if program.support is AnalysisSupport.LIMITED and not program.abstention_reasons:
        raise ValueError("limited program concordance requires a limitation reason")


class NeftelProgramConcordance(FrozenModel):
    program_index: int = Field(ge=0, lt=PROGRAM_COUNT)
    domain_id: Identifier
    program_id: str = Field(pattern=r"^(MES2|MES1|AC|OPC|NPC1|NPC2|G1/S|G2/M)$")
    program_name: NonEmptyStr
    output_semantics: Literal["conditional_program_concordance"] = "conditional_program_concordance"
    support: AnalysisSupport
    classification: ConditionalTransitionClassification
    score: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    unadjusted_program_coordinate: float | None = None
    global_adjustment: float | None = None
    interval_level: float = Field(default=0.9, ge=0.9, le=0.9)
    source_member_count: int = Field(ge=5, le=1_500)
    mapped_feature_count: int = Field(ge=5, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    fitted_feature_count: int = Field(ge=1, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    admitted_active_feature_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    active_feature_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    observed_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    left_censored_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    admitted_left_censored_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    coefficient_mass_coverage: float = Field(ge=0.0, le=1.0)
    unique_active_gene_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    unique_coefficient_mass: float = Field(ge=0.0, le=1.0)
    effective_sample_size: float = Field(ge=0.0)
    request_reconstruction_evaluable_fold_count: int = Field(default=0, ge=0, le=5)
    request_reconstruction_improved_fold_count: int = Field(default=0, ge=0, le=5)
    request_reconstruction_median_relative_gain: float | None = None
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    overlap_confounded: bool
    uncertainty: ConditionalUncertaintyDecomposition
    top_contributions: tuple[ConditionalProteinContribution, ...] = Field(
        default=(),
        max_length=MAX_TOP_CONTRIBUTIONS,
    )
    ablations: ConditionalProgramAblations
    abstention_reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def interpretation_matches_support_and_panel(self) -> Self:
        expected_domain, expected_neftel, expected_name = EXPECTED_PROGRAMS[self.program_index]
        if (
            self.domain_id,
            self.program_id,
            self.program_name,
        ) != (expected_domain, expected_neftel, expected_name):
            raise ValueError("program identity must match the locked Neftel panel order")
        if self.active_feature_count != self.observed_count + self.left_censored_count:
            raise ValueError(
                "informative program count must equal exact plus binding-censor counts"
            )
        if self.admitted_active_feature_count != (
            self.observed_count + self.admitted_left_censored_count
        ):
            raise ValueError("admitted program count must equal exact plus admitted-censor counts")
        if (
            self.admitted_active_feature_count < self.active_feature_count
            or self.admitted_left_censored_count < self.left_censored_count
        ):
            raise ValueError("informative program evidence cannot exceed admitted evidence")
        if self.unique_active_gene_count > self.active_feature_count:
            raise ValueError("unique active genes cannot exceed all active program genes")
        if (
            self.request_reconstruction_improved_fold_count
            > self.request_reconstruction_evaluable_fold_count
        ):
            raise ValueError(
                "improved request reconstruction evidence folds cannot exceed evaluable folds"
            )
        structural = self.ablations.required_structural()
        estimate = (
            self.score,
            self.lower_bound,
            self.upper_bound,
            self.unadjusted_program_coordinate,
            self.global_adjustment,
        )
        if self.support is AnalysisSupport.ABSTAINED:
            _validate_abstained_program(self, estimate)
        else:
            _validate_estimated_program(self, estimate, structural)
        return self


class NeftelProgramTransitionEvidence(FrozenModel):
    transition_id: Identifier
    transition_index: int = Field(ge=0, le=MAX_TIME_POINTS - 2)
    from_time_point_id: Identifier
    to_time_point_id: Identifier
    duration_days: float = Field(gt=0.0)
    global_transition: GlobalTransitionConcordance
    programs: tuple[NeftelProgramConcordance, ...] = Field(
        min_length=PROGRAM_COUNT,
        max_length=PROGRAM_COUNT,
    )

    @model_validator(mode="after")
    def program_family_is_complete_and_ordered(self) -> Self:
        if tuple(program.program_index for program in self.programs) != tuple(range(PROGRAM_COUNT)):
            raise ValueError("each transition must contain the complete fixed program order")
        if self.global_transition.support is AnalysisSupport.ABSTAINED and any(
            program.support is not AnalysisSupport.ABSTAINED for program in self.programs
        ):
            raise ValueError("programs must abstain when the global transition is not estimable")
        return self


class NeftelTransitionProvenance(FrozenModel):
    engine: Literal["kncc-neftel-program-transition/1.0.0"] = "kncc-neftel-program-transition/1.0.0"
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    computational_digest: Sha256Digest
    numerical_seed_digest: Sha256Digest
    source_catalog_artifact_digest: Sha256Digest
    source_catalog_content_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    neftel_source_program_digest: Sha256Digest
    program_order_digest: Sha256Digest
    program_membership_digest: Sha256Digest
    gene_order_digest: Sha256Digest
    patient_order_rule_digest: Sha256Digest
    fitted_artifact_digest: Sha256Digest
    fitted_content_digest: Sha256Digest
    fitted_source_catalog_binding_digest: Sha256Digest
    union_feature_digest: Sha256Digest
    program_inventory_digest: Sha256Digest
    membership_degree_digest: Sha256Digest
    reference_tensor_digest: Sha256Digest
    centering_scaling_digest: Sha256Digest
    reference_design_digest: Sha256Digest
    equal_membership_design_digest: Sha256Digest
    global_loading_digest: Sha256Digest
    conditional_loading_digest: Sha256Digest
    bootstrap_seed_namespace_digest: Sha256Digest
    bootstrap_ensemble_digest: Sha256Digest
    training_recipe_digest: Sha256Digest
    fold_policy_digest: Sha256Digest
    source_processing_ablation_digest: Sha256Digest
    evaluation_digest: Sha256Digest
    input_contract_schema_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    demo_semantic_oracle_digest: Sha256Digest
    assay_compatibility_digest: Sha256Digest
    normalization_reference_digest: Sha256Digest
    caller_evidence_set_digest: Sha256Digest
    numpy_version: NonEmptyStr
    bootstrap_seed: int = Field(ge=0, le=2**53 - 1)
    source_patient_count: Literal[104] = 104
    source_attribution: NonEmptyStr
    source_terms: tuple[NonEmptyStr, ...] = Field(min_length=2, max_length=4)
    source_transformation_notice: NonEmptyStr


class _NeftelTransitionResultDocument(FrozenModel):
    algorithm_id: Literal["kncc-neftel-program-transition"] = "kncc-neftel-program-transition"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-neftel-program-transition/1.0.0"] = (
        "kncc-neftel-program-transition/1.0.0"
    )
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    series_id: Identifier
    assay_compatibility: AssayCompatibilityAttestation
    normalization_reference: NormalizationReference
    time_point_ids: tuple[Identifier, ...] = Field(
        min_length=MIN_TIME_POINTS,
        max_length=MAX_TIME_POINTS,
    )
    transitions: tuple[NeftelProgramTransitionEvidence, ...] = Field(
        min_length=MIN_TIME_POINTS - 1,
        max_length=MAX_TIME_POINTS - 1,
    )
    provenance: NeftelTransitionProvenance
    output_semantics: Literal[
        "global_transition_concordance_and_conditional_program_concordance_only"
    ] = "global_transition_concordance_and_conditional_program_concordance_only"
    validation_scope: Literal["same_cohort_patient_grouped_evaluation_not_external_validation"] = (
        "same_cohort_patient_grouped_evaluation_not_external_validation"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=6, max_length=20)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def topology_and_provenance_are_consistent(self) -> Self:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("profile digest does not match provenance")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("request digest does not match provenance")
        if (
            sha256_digest(self.assay_compatibility.model_dump(mode="json"))
            != self.provenance.assay_compatibility_digest
        ):
            raise ValueError("assay compatibility digest does not match provenance")
        if self.normalization_reference.binding_digest != (
            self.provenance.normalization_reference_digest
        ):
            raise ValueError("normalization reference digest does not match provenance")
        if len(self.time_point_ids) != len(set(self.time_point_ids)):
            raise ValueError("result time-point identifiers must be unique")
        if len(self.transitions) != len(self.time_point_ids) - 1:
            raise ValueError("result must contain one transition per consecutive pair")
        transition_ids = tuple(transition.transition_id for transition in self.transitions)
        if len(transition_ids) != len(set(transition_ids)):
            raise ValueError("transition identifiers must be unique")
        for index, transition in enumerate(self.transitions):
            if transition.transition_index != index:
                raise ValueError("transition indices must be consecutive and zero-based")
            if (
                transition.from_time_point_id != self.time_point_ids[index]
                or transition.to_time_point_id != self.time_point_ids[index + 1]
            ):
                raise ValueError("transition endpoints must match consecutive time points")
        return self


class LongitudinalGbmNeftelTransitionResult(_NeftelTransitionResultDocument):
    """A locally generated, content-bound conditional-concordance receipt."""

    @model_validator(mode="after")
    def result_is_content_bound(self) -> Self:
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class UnverifiedLongitudinalGbmNeftelTransitionResult(_NeftelTransitionResultDocument):
    """A structurally valid caller receipt admitted only for exact replay."""


class NeftelProgramReplayVerificationRequest(FrozenModel):
    request: LongitudinalGbmNeftelTransitionRequest
    result: LongitudinalGbmNeftelTransitionResult | UnverifiedLongitudinalGbmNeftelTransitionResult


class NeftelProgramReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    transition_topology_match: bool
    global_transition_semantic_match: bool
    program_semantic_match: bool
    uncertainty_semantic_match: bool
    ablation_semantic_match: bool
    provenance_match: bool
    document_semantic_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr

    @model_validator(mode="after")
    def verification_summary_matches_components(self) -> Self:
        expected_semantic = all(
            (
                self.transition_topology_match,
                self.global_transition_semantic_match,
                self.program_semantic_match,
                self.uncertainty_semantic_match,
                self.ablation_semantic_match,
                self.provenance_match,
                self.document_semantic_match,
            )
        )
        if self.semantic_match is not expected_semantic:
            raise ValueError("semantic replay summary does not match its component checks")
        expected_verified = all(
            (
                self.request_digest_match,
                self.profile_digest_match,
                self.result_digest_match,
                self.semantic_match,
            )
        )
        if self.verified is not expected_verified:
            raise ValueError("replay verification summary does not match its checks")
        return self


class NeftelProgramAlgorithmConstants(FrozenModel):
    estimator: Literal["global_adjusted_robust_conditional_coordinate_v1"] = (
        "global_adjusted_robust_conditional_coordinate_v1"
    )
    missing_evidence_policy: Literal["missing_and_unsupported_never_become_negative_v1"] = (
        "missing_and_unsupported_never_become_negative_v1"
    )
    censoring_policy: Literal["reported_limit_one_sided_bound_v1"] = (
        "reported_limit_one_sided_bound_v1"
    )
    output_semantics: Literal[
        "global_transition_concordance_and_conditional_program_concordance_only"
    ] = "global_transition_concordance_and_conditional_program_concordance_only"
    huber_delta: float = Field(default=1.345, ge=1.345, le=1.345)
    ridge_lambda: float = Field(default=1.0, ge=1.0, le=1.0)
    global_ridge_multiplier: float = Field(default=0.25, ge=0.25, le=0.25)
    damping: float = Field(default=0.7, ge=0.7, le=0.7)
    solver_max_iterations: Literal[200] = 200
    solver_tolerance: float = Field(default=1e-9, ge=1e-9, le=1e-9)
    maximum_condition_number: float = Field(default=25.0, ge=25.0, le=25.0)
    minimum_evidence_reliability: float = Field(default=0.05, ge=0.05, le=0.05)
    censor_binding_tolerance: float = Field(default=1e-8, ge=1e-8, le=1e-8)
    interval_level: float = Field(default=0.9, ge=0.9, le=0.9)
    aligned_threshold: float = Field(default=0.25, ge=0.25, le=0.25)
    stable_threshold: float = Field(default=0.25, ge=0.25, le=0.25)
    default_bootstrap_replicates: Literal[64] = 64
    supported_minimum_bootstrap_replicates: Literal[64] = 64
    minimum_bootstrap_replicates: Literal[32] = 32
    maximum_bootstrap_replicates: Literal[256] = 256
    offline_bootstrap_ensemble_size: Literal[128] = 128
    global_minimum_active_genes: Literal[16] = 16
    global_minimum_exact_genes: Literal[16] = 16
    global_minimum_coefficient_mass: float = Field(default=0.25, ge=0.25, le=0.25)
    global_minimum_effective_sample_size: float = Field(default=8.0, ge=8.0, le=8.0)
    program_minimum_active_genes: Literal[5] = 5
    program_minimum_exact_genes: Literal[5] = 5
    program_minimum_coefficient_mass: float = Field(default=0.5, ge=0.5, le=0.5)
    program_minimum_effective_sample_size: float = Field(default=3.0, ge=3.0, le=3.0)
    program_minimum_unique_genes: Literal[3] = 3
    program_minimum_unique_mass: float = Field(default=0.2, ge=0.2, le=0.2)
    program_supported_minimum_stability: float = Field(default=0.8, ge=0.8, le=0.8)
    request_reconstruction_marker_folds: Literal[5] = 5
    program_supported_minimum_reconstruction_gain: float = Field(
        default=0.01,
        ge=0.01,
        le=0.01,
    )
    overlap_degree_policy: Literal["inverse_sqrt_program_membership_degree_v1"] = (
        "inverse_sqrt_program_membership_degree_v1"
    )
    outer_fold_salt: Literal["kncc-neftel-program-outer-v1"] = "kncc-neftel-program-outer-v1"
    marker_fold_salt: Literal["kncc-neftel-marker-fold-v1"] = "kncc-neftel-marker-fold-v1"
    quantization_decimals: Literal[8] = 8
    solver_work_unit_formula: Literal["(time_points - 1) * (186 + 3 * bootstrap_replicates)"] = (
        "(time_points - 1) * (186 + 3 * bootstrap_replicates)"
    )


class NeftelProgramLimits(FrozenModel):
    min_time_points: Literal[2] = 2
    max_time_points: Literal[16] = 16
    max_observations_per_time_point: Literal[4_096] = 4_096
    max_total_observations: Literal[12_000] = 12_000
    fixed_program_count: Literal[8] = 8
    max_top_contributions: Literal[10] = 10
    max_overlap_ablations: Literal[9] = 9
    request_max_bytes: Literal[2_097_152] = 2_097_152
    result_max_bytes: Literal[4_194_304] = 4_194_304
    replay_max_bytes: Literal[8_388_608] = 8_388_608
    max_solver_work_units: Literal[4_608] = 4_608


class NeftelProgramSourceModelCounts(FrozenModel):
    source_patient_count: Literal[104] = 104
    source_gene_count: Literal[11_312] = 11_312
    program_count: Literal[8] = 8
    mapped_union_feature_count: Literal[289] = 289
    fitted_union_feature_count: Literal[256] = 256
    fitted_global_feature_count: int = Field(ge=16, le=11_312)
    fitted_program_feature_count: int = Field(ge=5, le=11_312)
    offline_bootstrap_draw_count: Literal[128] = 128
    outer_fold_count: Literal[8] = 8
    marker_fold_count: Literal[5] = 5


class NeftelProgramSourceModelDigests(FrozenModel):
    source_catalog_artifact_digest: Sha256Digest
    source_catalog_content_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    neftel_source_program_digest: Sha256Digest
    program_order_digest: Sha256Digest
    program_membership_digest: Sha256Digest
    gene_order_digest: Sha256Digest
    patient_order_rule_digest: Sha256Digest
    fitted_artifact_digest: Sha256Digest
    fitted_content_digest: Sha256Digest
    fitted_source_catalog_binding_digest: Sha256Digest
    union_feature_digest: Sha256Digest
    program_inventory_digest: Sha256Digest
    membership_degree_digest: Sha256Digest
    reference_tensor_digest: Sha256Digest
    centering_scaling_digest: Sha256Digest
    reference_design_digest: Sha256Digest
    equal_membership_design_digest: Sha256Digest
    global_loading_digest: Sha256Digest
    conditional_loading_digest: Sha256Digest
    bootstrap_seed_namespace_digest: Sha256Digest
    bootstrap_ensemble_digest: Sha256Digest
    training_recipe_digest: Sha256Digest
    fold_policy_digest: Sha256Digest
    source_processing_ablation_digest: Sha256Digest
    evaluation_digest: Sha256Digest
    input_contract_schema_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest


class NeftelProgramEvaluationSummary(FrozenModel):
    """Locked same-cohort evidence ceiling; it is not external validation."""

    protocol: Literal[
        "eight deterministic held-patient folds with all source statistics and loadings "
        "refit; five deterministic held-marker folds within each held patient"
    ]
    validation_scope: Literal["same-cohort held-marker reconstruction; not external validation"]
    interpretation: Literal[
        "aggregate metrics compare a fitted conditional program dictionary with zero, "
        "global-only, and equal-membership baselines; individual program evidence is "
        "limited to its held-marker removal interval"
    ]
    release_gate: Literal["limited_fitted_dictionary_not_preferred_to_equal_membership"] = (
        "limited_fitted_dictionary_not_preferred_to_equal_membership"
    )
    patient_count: Literal[104] = 104
    evaluation_count: Literal[520] = 520
    union_feature_count: Literal[256] = 256
    zero_prediction_median_standardized_mae: float = Field(gt=0.0, le=2.0)
    global_only_median_standardized_mae: float = Field(gt=0.0, le=2.0)
    equal_membership_median_standardized_mae: float = Field(gt=0.0, le=2.0)
    joint_median_standardized_mae: float = Field(gt=0.0, le=2.0)
    joint_vs_global_median_relative_mae_gain: float = Field(gt=0.0, le=0.10)
    joint_vs_equal_median_relative_mae_gain: float = Field(ge=-0.25, lt=0.0)
    joint_vs_global_evaluation_improved_fraction: float = Field(ge=0.5, le=1.0)
    joint_vs_equal_evaluation_improved_fraction: float = Field(ge=0.0, lt=0.5)
    patient_cluster_joint_vs_global_median_gain: float = Field(gt=0.0, le=0.10)
    patient_cluster_joint_vs_equal_median_gain: float = Field(ge=-0.25, lt=0.0)
    patient_cluster_joint_vs_global_median_gain_90_interval: tuple[float, float]
    patient_cluster_joint_vs_equal_median_gain_90_interval: tuple[float, float]
    joint_vs_global_patient_cluster_interval_supports_positive_gain: Literal[True] = True
    joint_vs_equal_patient_cluster_interval_supports_positive_gain: Literal[False] = False
    patient_cluster_bootstrap_replicates: Literal[20_000] = 20_000
    reference_design_condition_number: float = Field(gt=0.0, le=25.0)
    equal_membership_reference_design_condition_number: float = Field(gt=0.0, le=25.0)
    outer_design_condition_minimum: float = Field(gt=0.0, le=25.0)
    outer_design_condition_maximum: float = Field(gt=0.0, le=25.0)
    outer_equal_membership_condition_minimum: float = Field(gt=0.0, le=25.0)
    outer_equal_membership_condition_maximum: float = Field(gt=0.0, le=25.0)
    minimum_outer_loading_cosine: float = Field(ge=0.97, le=1.0)
    full_patient_nonconverged_count: Literal[0] = 0
    global_held_marker_nonconverged_count: Literal[0] = 0
    equal_membership_held_marker_nonconverged_count: Literal[0] = 0
    joint_held_marker_nonconverged_count: Literal[0] = 0
    leave_program_out_nonconverged_count: Literal[0] = 0
    all_primary_solver_fits_converged: Literal[True] = True
    individually_supported_program_count: Literal[0] = 0
    leave_program_interval_count: Literal[8] = 8
    all_leave_program_q05_q95_intervals_cross_zero: Literal[True] = True

    @model_validator(mode="after")
    def metrics_expose_only_the_locked_modest_evidence(self) -> Self:
        if not (
            self.equal_membership_median_standardized_mae
            < self.joint_median_standardized_mae
            < self.global_only_median_standardized_mae
            < self.zero_prediction_median_standardized_mae
        ):
            raise ValueError("same-cohort median MAE ordering is inconsistent")
        global_lower, global_upper = self.patient_cluster_joint_vs_global_median_gain_90_interval
        if not (
            0.0
            < global_lower
            <= self.patient_cluster_joint_vs_global_median_gain
            <= global_upper
            <= 0.10
        ):
            raise ValueError("patient-cluster joint-vs-global interval is inconsistent")
        equal_lower, equal_upper = self.patient_cluster_joint_vs_equal_median_gain_90_interval
        if not (
            -0.25
            <= equal_lower
            <= self.patient_cluster_joint_vs_equal_median_gain
            <= equal_upper
            < 0.0
        ):
            raise ValueError("patient-cluster joint-vs-equal interval is inconsistent")
        if not (
            self.outer_design_condition_minimum
            <= self.reference_design_condition_number
            <= self.outer_design_condition_maximum
        ):
            raise ValueError("reference condition must lie within held-fold condition bounds")
        if not (
            self.outer_equal_membership_condition_minimum
            <= self.equal_membership_reference_design_condition_number
            <= self.outer_equal_membership_condition_maximum
        ):
            raise ValueError(
                "equal-membership condition must lie within held-fold condition bounds"
            )
        return self


class NeftelProgramProfile(FrozenModel):
    program_index: int = Field(ge=0, lt=PROGRAM_COUNT)
    domain_id: Identifier
    program_id: str = Field(pattern=r"^(MES2|MES1|AC|OPC|NPC1|NPC2|G1/S|G2/M)$")
    program_name: NonEmptyStr
    source_member_count: int = Field(ge=5, le=1_500)
    mapped_feature_count: int = Field(ge=5, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    eligible_feature_count: int = Field(ge=5, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    fitted_feature_count: int = Field(ge=5, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    unique_fitted_feature_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    overlap_confounded: bool

    @model_validator(mode="after")
    def identity_matches_catalog(self) -> Self:
        expected_domain, expected_neftel, expected_name = EXPECTED_PROGRAMS[self.program_index]
        if (
            self.domain_id,
            self.program_id,
            self.program_name,
        ) != (expected_domain, expected_neftel, expected_name):
            raise ValueError("profile program identity must match the locked panel")
        if (
            self.eligible_feature_count > self.mapped_feature_count
            or self.fitted_feature_count > self.mapped_feature_count
            or self.unique_fitted_feature_count > self.fitted_feature_count
        ):
            raise ValueError("profile fitted feature counts must be nested within mapped support")
        return self


class LongitudinalGbmNeftelTransitionProfile(FrozenModel):
    algorithm_id: Literal["kncc-neftel-program-transition"] = "kncc-neftel-program-transition"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-neftel-program-transition/1.0.0"] = (
        "kncc-neftel-program-transition/1.0.0"
    )
    model_id: Literal["kncc-neftel-program-transition-model/1.0.0"] = (
        "kncc-neftel-program-transition-model/1.0.0"
    )
    parent_feature_axis_model_id: Literal["kncc-paired-protein-transition/1.0.0"] = (
        "kncc-paired-protein-transition/1.0.0"
    )
    parent_dependency_semantics: Literal[
        "feature_axis_and_assay_binding_only_no_runtime_delegation"
    ] = "feature_axis_and_assay_binding_only_no_runtime_delegation"
    required_assay_compatibility: AssayCompatibilityAttestation
    constants: NeftelProgramAlgorithmConstants
    limits: NeftelProgramLimits
    counts: NeftelProgramSourceModelCounts
    digests: NeftelProgramSourceModelDigests
    evaluation: NeftelProgramEvaluationSummary
    programs: tuple[NeftelProgramProfile, ...] = Field(
        min_length=PROGRAM_COUNT,
        max_length=PROGRAM_COUNT,
    )
    numpy_version: NonEmptyStr
    demo_id: Identifier
    demo_request_digest: Sha256Digest
    demo_semantic_oracle_digest: Sha256Digest
    source_attribution: NonEmptyStr
    source_terms: tuple[NonEmptyStr, ...] = Field(min_length=2, max_length=4)
    source_transformation_notice: NonEmptyStr
    profile_digest: Sha256Digest
    safety_class: Literal["research_use_only"] = "research_use_only"
    claim_ceiling: Literal[
        "paired_source_cohort_bulk_protein_program_transition_concordance_only"
    ] = "paired_source_cohort_bulk_protein_program_transition_concordance_only"
    interpretation: Literal[
        "global_adjusted_neftel_program_coordinate_not_recurrence_prediction_evolution_"
        "subtype_deconvolution_or_activation"
    ] = (
        "global_adjusted_neftel_program_coordinate_not_recurrence_prediction_evolution_"
        "subtype_deconvolution_or_activation"
    )
    maximum_evidence_grade: Literal["limited_same_cohort_without_external_validation"] = (
        "limited_same_cohort_without_external_validation"
    )

    @model_validator(mode="after")
    def profile_is_complete_ordered_and_content_bound(self) -> Self:
        if tuple(program.program_index for program in self.programs) != tuple(range(PROGRAM_COUNT)):
            raise ValueError("profile must contain the complete fixed program order")
        if self.profile_digest != profile_payload_digest(self):
            raise ValueError("profile digest does not match canonical profile content")
        return self


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_PROFILE_ID",
    "ALGORITHM_VERSION",
    "DEFAULT_BOOTSTRAPS",
    "GLOBAL_MIN_ACTIVE_GENES",
    "GLOBAL_MIN_COEFFICIENT_MASS",
    "GLOBAL_MIN_EFFECTIVE_SAMPLE_SIZE",
    "GLOBAL_MIN_EXACT_GENES",
    "MAX_BOOTSTRAPS",
    "MAX_OBSERVATIONS_PER_TIME_POINT",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "MAX_SOLVER_WORK_UNITS",
    "MAX_TIME_POINTS",
    "MAX_TOTAL_OBSERVATIONS",
    "MIN_BOOTSTRAPS",
    "MIN_TIME_POINTS",
    "MODEL_ID",
    "PROFILE_ID",
    "PROGRAM_COUNT",
    "PROGRAM_MIN_ACTIVE_GENES",
    "PROGRAM_MIN_COEFFICIENT_MASS",
    "PROGRAM_MIN_EFFECTIVE_SAMPLE_SIZE",
    "PROGRAM_MIN_EXACT_GENES",
    "PROGRAM_MIN_UNIQUE_GENES",
    "PROGRAM_MIN_UNIQUE_MASS",
    "REQUIRED_ASSAY_COMPATIBILITY",
    "SOLVER_BOOTSTRAP_WORK_UNITS_PER_REPLICATE",
    "SOLVER_FIXED_WORK_UNITS_PER_TRANSITION",
    "AnalysisSupport",
    "AssayCompatibilityAttestation",
    "ConditionalComponentAblation",
    "ConditionalProgramAblations",
    "ConditionalProteinContribution",
    "ConditionalTransitionClassification",
    "ConditionalUncertaintyDecomposition",
    "ContributionDirection",
    "GlobalTransitionClassification",
    "GlobalTransitionConcordance",
    "LongitudinalGbmNeftelTransitionProfile",
    "LongitudinalGbmNeftelTransitionRequest",
    "LongitudinalGbmNeftelTransitionResult",
    "LongitudinalTimePoint",
    "NeftelProgramAlgorithmConstants",
    "NeftelProgramConcordance",
    "NeftelProgramEvaluationSummary",
    "NeftelProgramLimits",
    "NeftelProgramProfile",
    "NeftelProgramReplayVerificationRequest",
    "NeftelProgramReplayVerificationResult",
    "NeftelProgramSourceModelCounts",
    "NeftelProgramSourceModelDigests",
    "NeftelProgramTransitionEvidence",
    "NeftelTransitionProvenance",
    "NormalizationReference",
    "ProteinEvidenceState",
    "ProteinObservation",
    "UncertaintyState",
    "UnverifiedLongitudinalGbmNeftelTransitionResult",
    "ValueSemantics",
]
