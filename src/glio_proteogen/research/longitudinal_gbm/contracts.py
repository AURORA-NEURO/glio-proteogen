"""Strict contracts for KNCC-derived longitudinal GBM protein concordance.

The lane compares caller-supplied, ordered protein measurements with a frozen
primary-to-recurrence source model.  Its outputs are research evidence about
protein-level concordance.  They are not tumor-evolution truth, molecular subtype,
diagnosis, prognosis, treatment guidance, or a claim that two specimens share identity.
"""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Self, cast

from pydantic import Field, StringConstraints, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .canonical import (
    canonical_request_digest,
    profile_payload_digest,
    result_payload_digest,
    sha256_digest,
)

ALGORITHM_ID = "kncc-gbm-longitudinal-concordance"
ALGORITHM_VERSION = "1.0.0"
ALGORITHM_PROFILE_ID = "kncc-gbm-longitudinal-concordance/1.0.0"
PROFILE_ID = ALGORITHM_PROFILE_ID
MIN_TIME_POINTS = 2
MAX_TIME_POINTS = 16
MAX_OBSERVATIONS_PER_TIME_POINT = 4_096
MAX_TOTAL_OBSERVATIONS = 12_000
MIN_BOOTSTRAPS = 32
DEFAULT_BOOTSTRAPS = 128
MAX_BOOTSTRAPS = 256
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 4 * 1_024 * 1_024
MAX_REPLAY_BYTES = 8 * 1_024 * 1_024

HgncGeneSymbol = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=32,
        pattern=r"^[A-Z0-9][A-Z0-9._/-]*$",
    ),
]


class ProteinEvidenceState(StrEnum):
    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class AnalysisSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class TransitionClassification(StrEnum):
    SOURCE_RECURRENCE_ALIGNED = "source_recurrence_aligned"
    REVERSE_ALIGNED = "reverse_aligned"
    STABLE = "stable"
    INDETERMINATE = "indeterminate"
    NOT_ESTIMABLE = "not_estimable"


class UncertaintyState(StrEnum):
    ESTIMATED = "estimated"
    NOT_ESTIMABLE = "not_estimable"


class DriverDirection(StrEnum):
    SOURCE_RECURRENCE_ALIGNED = "source_recurrence_aligned"
    REVERSE_ALIGNED = "reverse_aligned"


class AssayCompatibilityAttestation(FrozenModel):
    """Exact caller attestation required before applying the frozen KNCC scale.

    Every field is deliberately required (there are no defaults).  A missing field,
    an alternate assay, ordinary/shared-peptide quantification, or a non-log2 value
    therefore fails validation instead of being silently projected onto the
    PDC000514 TMT11 ``Unshared Log`` model.
    """

    schema_version: Literal["glio-proteogen.kncc-assay-compatibility-attestation/1.0.0"]
    compatibility_profile_id: Literal["kncc-pdc000514-tmt11-unshared-log2-ratio/1.0.0"]
    source_profile_content_digest: Literal[
        "sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3"
    ]
    assay: Literal["tmt11_plexed_mass_spectrometry"]
    quantification: Literal["unshared_peptide_protein_abundance_ratio"]
    value_transformation: Literal["log2_ratio"]
    log_base: Literal[2]
    invariant_across_time_points: Literal[True]
    attested_compatible: Literal[True]


REQUIRED_ASSAY_COMPATIBILITY = AssayCompatibilityAttestation(
    schema_version="glio-proteogen.kncc-assay-compatibility-attestation/1.0.0",
    compatibility_profile_id="kncc-pdc000514-tmt11-unshared-log2-ratio/1.0.0",
    source_profile_content_digest=(
        "sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3"
    ),
    assay="tmt11_plexed_mass_spectrometry",
    quantification="unshared_peptide_protein_abundance_ratio",
    value_transformation="log2_ratio",
    log_base=2,
    invariant_across_time_points=True,
    attested_compatible=True,
)


class NormalizationReference(FrozenModel):
    """One caller-owned preprocessing/reference binding shared by every time point."""

    reference_id: Identifier
    binding_digest: Sha256Digest
    normalization_method: NonEmptyStr
    abundance_scale: Literal["caller_supplied_log2_protein_abundance_ratio"] = (
        "caller_supplied_log2_protein_abundance_ratio"
    )
    invariant_across_time_points: Literal[True] = True


class ProteinObservation(FrozenModel):
    observation_id: Identifier
    gene_symbol: HgncGeneSymbol
    state: ProteinEvidenceState
    log_abundance: float | None = Field(default=None, ge=-100.0, le=100.0)
    standard_error: float | None = Field(default=None, gt=0.0, le=20.0)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_digest: Sha256Digest

    @model_validator(mode="after")
    def numerical_values_match_state(self) -> Self:
        active = self.state in {
            ProteinEvidenceState.OBSERVED,
            ProteinEvidenceState.LEFT_CENSORED,
        }
        if active and (self.log_abundance is None or self.standard_error is None):
            raise ValueError(
                "observed and left-censored protein evidence require log abundance and error"
            )
        if active and self.quality_weight <= 0.0:
            raise ValueError("active protein evidence requires positive quality")
        if not active and (self.log_abundance is not None or self.standard_error is not None):
            raise ValueError("missing and unsupported protein evidence cannot carry numeric values")
        if not active and self.quality_weight != 0.0:
            raise ValueError("missing and unsupported protein evidence must have zero quality")
        return self


class LongitudinalTimePoint(FrozenModel):
    time_point_id: Identifier
    time_offset_days: float = Field(ge=0.0)
    normalization_reference_digest: Sha256Digest
    observations: tuple[ProteinObservation, ...] = Field(
        min_length=1,
        max_length=MAX_OBSERVATIONS_PER_TIME_POINT,
    )

    @field_validator("observations")
    @classmethod
    def observations_are_unique(
        cls,
        values: tuple[ProteinObservation, ...],
    ) -> tuple[ProteinObservation, ...]:
        observation_ids = tuple(item.observation_id for item in values)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError(f"{cls.__name__} observation identifiers must be unique")
        gene_symbols = tuple(item.gene_symbol for item in values)
        if len(gene_symbols) != len(set(gene_symbols)):
            raise ValueError(f"{cls.__name__} HGNC gene symbols must be unique")
        return values


class LongitudinalGbmRequest(FrozenModel):
    profile_id: Literal["kncc-gbm-longitudinal-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-concordance/1.0.0"
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
                f"longitudinal requests are limited to {MAX_TOTAL_OBSERVATIONS} observations"
            )
        return self

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class TransitionUncertainty(FrozenModel):
    state: UncertaintyState
    standard_error: float | None = Field(default=None, ge=0.0)
    variance_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    bootstrap_replicates_used: int = Field(default=0, ge=0, le=MAX_BOOTSTRAPS)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def statistics_match_state(self) -> Self:
        if self.state is UncertaintyState.ESTIMATED:
            if self.standard_error is None or self.bootstrap_replicates_used == 0:
                raise ValueError(
                    "estimated uncertainty requires a standard error and bootstrap replicates"
                )
            if self.reason is not None:
                raise ValueError("estimated uncertainty cannot carry an abstention reason")
        else:
            if self.standard_error is not None or self.variance_fraction is not None:
                raise ValueError("non-estimable uncertainty cannot carry numeric statistics")
            if self.bootstrap_replicates_used != 0 or self.reason is None:
                raise ValueError(
                    "non-estimable uncertainty requires a reason and zero bootstrap replicates"
                )
        return self


class UncertaintyInteraction(FrozenModel):
    """Paired-bootstrap covariance term in the exact variance identity."""

    state: UncertaintyState
    method: Literal["paired_bootstrap_covariance_identity_v1"] = (
        "paired_bootstrap_covariance_identity_v1"
    )
    covariance: float | None = None
    variance_contribution: float | None = None
    combined_variance: float | None = Field(default=None, ge=0.0)
    decomposition_residual: float | None = Field(default=None, ge=0.0)
    bootstrap_replicates_used: int = Field(default=0, ge=0, le=MAX_BOOTSTRAPS)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def statistics_match_state(self) -> Self:
        statistics = (
            self.covariance,
            self.variance_contribution,
            self.combined_variance,
            self.decomposition_residual,
        )
        if self.state is UncertaintyState.ESTIMATED:
            if any(value is None for value in statistics) or self.bootstrap_replicates_used == 0:
                raise ValueError(
                    "estimated uncertainty interaction requires covariance statistics and "
                    "bootstrap replicates"
                )
            if self.reason is not None:
                raise ValueError("estimated uncertainty interaction cannot carry a reason")
        else:
            if any(value is not None for value in statistics):
                raise ValueError(
                    "non-estimable uncertainty interaction cannot carry numeric statistics"
                )
            if self.bootstrap_replicates_used != 0 or self.reason is None:
                raise ValueError(
                    "non-estimable uncertainty interaction requires a reason and zero "
                    "bootstrap replicates"
                )
        return self


class SignedProteinDriver(FrozenModel):
    gene_symbol: HgncGeneSymbol
    source_gene_label: NonEmptyStr
    from_observation_id: Identifier
    to_observation_id: Identifier
    from_provenance_digest: Sha256Digest
    to_provenance_digest: Sha256Digest
    from_state: Literal[ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED]
    to_state: Literal[ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED]
    value_semantics: Literal["exact_delta", "upper_bound", "lower_bound"]
    standardized_delta: float
    model_coefficient: float
    signed_contribution: float
    direction: DriverDirection
    reliability_weight: float = Field(gt=0.0)
    source_feature_support: int = Field(ge=1, le=104)


class _AblationEstimate(FrozenModel):
    support: AnalysisSupport
    score_without_component: float | None = None
    score_delta: float | None = None
    classification_without_component: TransitionClassification
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def estimate_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if self.score_without_component is not None or self.score_delta is not None:
                raise ValueError("abstained ablations cannot carry numeric estimates")
            if self.classification_without_component is not TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("abstained ablations must be not_estimable")
            if self.reason is None:
                raise ValueError("abstained ablations require a reason")
        else:
            if self.score_without_component is None or self.score_delta is None:
                raise ValueError("estimated ablations require score and score delta")
            if self.classification_without_component is TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("estimated ablations cannot be not_estimable")
            if self.support is AnalysisSupport.SUPPORTED and self.reason is not None:
                raise ValueError("supported ablations cannot carry a limitation reason")
            if self.support is AnalysisSupport.LIMITED and self.reason is None:
                raise ValueError("limited ablations require a limitation reason")
        return self


class SourceProcessingAblation(_AblationEstimate):
    comparison: NonEmptyStr


class TopDriverAblation(_AblationEstimate):
    omitted_gene_symbol: HgncGeneSymbol
    omitted_signed_contribution: float


class TransitionEvidence(FrozenModel):
    transition_id: Identifier
    transition_index: int = Field(ge=0, le=MAX_TIME_POINTS - 2)
    from_time_point_id: Identifier
    to_time_point_id: Identifier
    support: AnalysisSupport
    classification: TransitionClassification
    score: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    interval_level: float = Field(default=0.9, ge=0.9, le=0.9)
    bootstrap_replicates_used: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    shared_active_gene_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    effective_sample_size: float = Field(ge=0.0)
    coverage: float = Field(ge=0.0, le=1.0)
    source_support_percentile: float | None = Field(default=None, ge=0.0, le=1.0)
    measurement_uncertainty: TransitionUncertainty
    coefficient_uncertainty: TransitionUncertainty
    uncertainty_interaction: UncertaintyInteraction
    top_drivers: tuple[SignedProteinDriver, ...] = Field(default=(), max_length=10)
    source_processing_ablations: tuple[SourceProcessingAblation, ...] = Field(
        default=(),
        max_length=8,
    )
    top_driver_ablations: tuple[TopDriverAblation, ...] = Field(default=(), max_length=10)
    abstention_reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def interpretation_matches_support(self) -> Self:
        estimate = (self.score, self.lower_bound, self.upper_bound)
        if self.support is AnalysisSupport.ABSTAINED:
            if self.classification is not TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("abstained transitions must be not_estimable")
            if any(value is not None for value in estimate):
                raise ValueError("abstained transitions cannot carry an interval estimate")
            if self.source_support_percentile is not None:
                raise ValueError("abstained transitions cannot carry a source-support percentile")
            if self.bootstrap_replicates_used != 0 or not self.abstention_reasons:
                raise ValueError(
                    "abstained transitions require reasons and zero bootstrap replicates"
                )
            if (
                self.measurement_uncertainty.state is not UncertaintyState.NOT_ESTIMABLE
                or self.coefficient_uncertainty.state is not UncertaintyState.NOT_ESTIMABLE
                or self.uncertainty_interaction.state is not UncertaintyState.NOT_ESTIMABLE
            ):
                raise ValueError(
                    "abstained transitions require non-estimable uncertainty and interaction"
                )
        else:
            if any(value is None for value in estimate):
                raise ValueError("estimated transitions require a complete 90% interval")
            score = cast("float", self.score)
            lower = cast("float", self.lower_bound)
            upper = cast("float", self.upper_bound)
            if not lower <= score <= upper:
                raise ValueError("transition interval must contain its score")
            if self.classification is TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("estimated transitions cannot be not_estimable")
            if self.source_support_percentile is None:
                raise ValueError("estimated transitions require a source-support percentile")
            if self.bootstrap_replicates_used == 0:
                raise ValueError("estimated transitions require bootstrap replicates")
            if (
                self.measurement_uncertainty.state is not UncertaintyState.ESTIMATED
                or self.coefficient_uncertainty.state is not UncertaintyState.ESTIMATED
                or self.uncertainty_interaction.state is not UncertaintyState.ESTIMATED
            ):
                raise ValueError(
                    "estimated transitions require both uncertainty components and their "
                    "interaction"
                )
            if self.support is AnalysisSupport.SUPPORTED and self.abstention_reasons:
                raise ValueError("supported transitions cannot carry limitation reasons")
            if self.support is AnalysisSupport.LIMITED and not self.abstention_reasons:
                raise ValueError("limited transitions require a limitation reason")
        return self


class PeltBoundary(FrozenModel):
    boundary_index: int = Field(ge=1, le=MAX_TIME_POINTS - 1)
    left_time_point_id: Identifier
    right_time_point_id: Identifier
    cost_reduction: float = Field(ge=0.0)
    bootstrap_frequency: float = Field(ge=0.0, le=1.0)


class PeltAnalysis(FrozenModel):
    method: Literal["exact_pelt_duration_normalized_transition_rate_huber_v2"] = (
        "exact_pelt_duration_normalized_transition_rate_huber_v2"
    )
    support: AnalysisSupport
    penalty: float = Field(gt=0.0)
    objective_value: float | None = Field(default=None, ge=0.0)
    bootstrap_replicates_used: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    boundaries: tuple[PeltBoundary, ...] = Field(default=(), max_length=MAX_TIME_POINTS - 1)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def analysis_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if self.objective_value is not None or self.boundaries:
                raise ValueError("abstained PELT analysis cannot carry results")
            if self.bootstrap_replicates_used != 0 or self.reason is None:
                raise ValueError(
                    "abstained PELT analysis requires a reason and zero bootstrap replicates"
                )
        else:
            if self.objective_value is None or self.bootstrap_replicates_used == 0:
                raise ValueError("estimated PELT analysis requires objective and bootstraps")
            if self.support is AnalysisSupport.SUPPORTED and self.reason is not None:
                raise ValueError("supported PELT analysis cannot carry a limitation reason")
            if self.support is AnalysisSupport.LIMITED and self.reason is None:
                raise ValueError("limited PELT analysis requires a limitation reason")
            indices = tuple(boundary.boundary_index for boundary in self.boundaries)
            if len(indices) != len(set(indices)):
                raise ValueError("PELT boundary indices must be unique")
        return self


class LongitudinalGbmProvenance(FrozenModel):
    engine: Literal["kncc-gbm-longitudinal-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-concordance/1.0.0"
    )
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    source_profile_content_digest: Sha256Digest
    source_profile_artifact_digest: Sha256Digest
    source_file_lock_digest: Sha256Digest
    cohort_oracle_digest: Sha256Digest
    feature_space_digest: Sha256Digest
    transition_model_digest: Sha256Digest
    coefficient_digest: Sha256Digest
    bootstrap_digest: Sha256Digest
    source_processing_ablation_digest: Sha256Digest
    hgnc_complete_set_digest: Sha256Digest
    source_to_hgnc_mapping_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    demo_semantic_oracle_digest: Sha256Digest
    assay_compatibility_digest: Sha256Digest
    normalization_reference_digest: Sha256Digest
    numpy_version: NonEmptyStr
    computational_digest: Sha256Digest
    numerical_seed_digest: Sha256Digest
    bootstrap_seed: int = Field(ge=0, le=2**53 - 1)
    observation_source_digests: tuple[Sha256Digest, ...] = Field(max_length=MAX_TOTAL_OBSERVATIONS)
    source_attribution: NonEmptyStr
    source_license: NonEmptyStr
    source_license_url: NonEmptyStr
    source_transformation_notice: NonEmptyStr


class _LongitudinalGbmResultDocument(FrozenModel):
    algorithm_id: Literal["kncc-gbm-longitudinal-concordance"] = "kncc-gbm-longitudinal-concordance"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-gbm-longitudinal-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-concordance/1.0.0"
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
    transitions: tuple[TransitionEvidence, ...] = Field(
        min_length=MIN_TIME_POINTS - 1,
        max_length=MAX_TIME_POINTS - 1,
    )
    pelt_analysis: PeltAnalysis | None = None
    provenance: LongitudinalGbmProvenance
    output_semantics: Literal["protein_level_longitudinal_source_concordance"] = (
        "protein_level_longitudinal_source_concordance"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def result_topology_and_provenance_are_consistent(self) -> Self:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("profile digest does not match provenance")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("request digest does not match provenance")
        if (
            sha256_digest(self.assay_compatibility.model_dump(mode="json"))
            != self.provenance.assay_compatibility_digest
        ):
            raise ValueError("assay compatibility attestation digest does not match provenance")
        if (
            self.normalization_reference.binding_digest
            != self.provenance.normalization_reference_digest
        ):
            raise ValueError("normalization/reference digest does not match provenance")
        if len(self.time_point_ids) != len(set(self.time_point_ids)):
            raise ValueError("result time-point identifiers must be unique")
        if len(self.transitions) != len(self.time_point_ids) - 1:
            raise ValueError("result must contain exactly one transition per consecutive pair")
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

        if self.pelt_analysis is not None:
            if len(self.time_point_ids) < 4:
                raise ValueError("rate-based PELT analysis requires at least four time points")
            for boundary in self.pelt_analysis.boundaries:
                if boundary.boundary_index >= len(self.time_point_ids) - 1:
                    raise ValueError("PELT boundary index is outside the time series")
                if (
                    boundary.left_time_point_id != self.time_point_ids[boundary.boundary_index - 1]
                    or boundary.right_time_point_id != self.time_point_ids[boundary.boundary_index]
                ):
                    raise ValueError("PELT boundary endpoints do not match its exact index")
            endpoints = (
                0,
                *(boundary.boundary_index for boundary in self.pelt_analysis.boundaries),
                len(self.transitions),
            )
            if any(end - start < 2 for start, end in pairwise(endpoints)):
                raise ValueError("PELT rate segments require at least two transitions")
        return self


class LongitudinalGbmResult(_LongitudinalGbmResultDocument):
    """A content-verified result generated by the local engine."""

    @model_validator(mode="after")
    def result_is_content_bound(self) -> Self:
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class UnverifiedLongitudinalGbmResult(_LongitudinalGbmResultDocument):
    """A caller receipt accepted structurally before exact replay verification."""


class ReplayVerificationRequest(FrozenModel):
    request: LongitudinalGbmRequest
    result: LongitudinalGbmResult | UnverifiedLongitudinalGbmResult


class ReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    transition_semantic_match: bool
    pelt_semantic_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr


class LongitudinalAlgorithmConstants(FrozenModel):
    transition_estimator: NonEmptyStr
    feature_scaling_policy: NonEmptyStr
    missing_evidence_policy: Literal["missing_and_unsupported_never_become_negative_v1"]
    censoring_policy: NonEmptyStr
    measurement_uncertainty_policy: NonEmptyStr
    coefficient_uncertainty_policy: NonEmptyStr
    uncertainty_interaction_policy: Literal["paired_bootstrap_covariance_identity_v1"]
    source_processing_ablation_policy: NonEmptyStr
    top_driver_ablation_policy: NonEmptyStr
    change_point_estimator: Literal["exact_pelt_duration_normalized_transition_rate_huber_v2"]
    pelt_time_axis_policy: Literal["duration_normalized_transition_rates_per_90_days_v2"]
    huber_delta: float = Field(gt=0.0)
    location_ridge: float = Field(gt=0.0)
    location_solver_iterations: int = Field(ge=16, le=256)
    location_search_bound: float = Field(gt=0.0)
    standard_error_floor: float = Field(gt=0.0)
    default_bootstrap_replicates: Literal[128] = 128
    minimum_bootstrap_replicates: Literal[32] = 32
    maximum_bootstrap_replicates: Literal[256] = 256
    interval_lower_quantile: float = Field(default=0.05, ge=0.05, le=0.05)
    interval_upper_quantile: float = Field(default=0.95, ge=0.95, le=0.95)
    alignment_threshold: float = Field(gt=0.0)
    stable_threshold: float = Field(ge=0.0)
    supported_minimum_shared_genes: int = Field(gt=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    supported_minimum_coverage: float = Field(gt=0.0, le=1.0)
    supported_minimum_effective_sample_size: float = Field(gt=0.0)
    supported_minimum_bootstrap_replicates: Literal[64] = 64
    pelt_minimum_time_points: Literal[4] = 4
    pelt_minimum_segment_transitions: Literal[2] = 2
    pelt_rate_reference_days: float = Field(default=90.0, ge=90.0, le=90.0)
    pelt_penalty: float = Field(gt=0.0)
    maximum_top_drivers: int = Field(gt=0, le=10)
    quantization_decimals: int = Field(ge=0, le=15)
    random_seed_bytes: int = Field(ge=4, le=32)

    @model_validator(mode="after")
    def thresholds_are_nested(self) -> Self:
        if self.stable_threshold >= self.alignment_threshold:
            raise ValueError("stable threshold must be below the alignment threshold")
        return self


class LongitudinalSourceModelCounts(FrozenModel):
    """Audited v1 source/cohort/model cardinalities without patient identifiers."""

    pdc_source_row_label_count: Literal[11_323] = 11_323
    pdc_biological_row_label_count: Literal[11_320] = 11_320
    aggregate_row_label_count: Literal[3] = 3
    strict_paired_transition_count: Literal[104] = 104
    hgnc_exact_approved_source_label_count: Literal[11_232] = 11_232
    hgnc_unique_alias_source_label_count: Literal[80] = 80
    hgnc_ambiguous_source_label_count: Literal[4] = 4
    hgnc_unresolved_source_label_count: Literal[4] = 4
    hgnc_colliding_approved_symbol_count: Literal[0] = 0
    hgnc_admitted_feature_count: Literal[11_312] = 11_312
    excluded_specimen_label_count: Literal[6] = 6
    excluded_patient_group_count: Literal[5] = 5
    source_file_count: int = Field(ge=1, le=32)
    fitted_feature_count: int = Field(ge=1, le=11_320)
    nonzero_coefficient_count: int = Field(ge=1, le=11_320)
    nested_cv_outer_folds: int = Field(ge=2)
    nested_cv_inner_folds: int = Field(ge=2)

    @model_validator(mode="after")
    def model_counts_are_coherent(self) -> Self:
        if self.fitted_feature_count > self.hgnc_admitted_feature_count:
            raise ValueError("fitted features cannot exceed HGNC-mapped features")
        if self.nonzero_coefficient_count > self.fitted_feature_count:
            raise ValueError("nonzero coefficients cannot exceed fitted features")
        return self


class LongitudinalSourceModelDigests(FrozenModel):
    source_profile_content_digest: Sha256Digest
    source_profile_artifact_digest: Sha256Digest
    source_file_lock_digest: Sha256Digest
    cohort_oracle_digest: Sha256Digest
    feature_space_digest: Sha256Digest
    transition_model_digest: Sha256Digest
    coefficient_digest: Sha256Digest
    bootstrap_digest: Sha256Digest
    source_processing_ablation_digest: Sha256Digest
    hgnc_complete_set_digest: Sha256Digest
    source_to_hgnc_mapping_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest


class LongitudinalGbmProfile(FrozenModel):
    algorithm_id: Literal["kncc-gbm-longitudinal-concordance"] = "kncc-gbm-longitudinal-concordance"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-gbm-longitudinal-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-concordance/1.0.0"
    )
    model_id: Literal["kncc-paired-protein-transition/1.0.0"] = (
        "kncc-paired-protein-transition/1.0.0"
    )
    required_assay_compatibility: AssayCompatibilityAttestation
    constants: LongitudinalAlgorithmConstants
    counts: LongitudinalSourceModelCounts
    digests: LongitudinalSourceModelDigests
    numpy_version: NonEmptyStr
    demo_id: Identifier
    demo_request_digest: Sha256Digest
    demo_semantic_oracle_digest: Sha256Digest
    source_attribution: NonEmptyStr
    source_license: NonEmptyStr
    source_license_url: NonEmptyStr
    source_transformation_notice: NonEmptyStr
    profile_digest: Sha256Digest
    safety_class: Literal["research_use_only"] = "research_use_only"
    claim_ceiling: Literal[
        "protein_level_longitudinal_concordance_research_only_non_prescriptive"
    ] = "protein_level_longitudinal_concordance_research_only_non_prescriptive"
    interpretation: Literal["source_aligned_transition_evidence_not_patient_evolution"] = (
        "source_aligned_transition_evidence_not_patient_evolution"
    )

    @model_validator(mode="after")
    def profile_is_content_bound(self) -> Self:
        if self.profile_digest != profile_payload_digest(self):
            raise ValueError("profile digest does not match canonical profile content")
        return self


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_PROFILE_ID",
    "ALGORITHM_VERSION",
    "DEFAULT_BOOTSTRAPS",
    "MAX_BOOTSTRAPS",
    "MAX_OBSERVATIONS_PER_TIME_POINT",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "MAX_TIME_POINTS",
    "MAX_TOTAL_OBSERVATIONS",
    "MIN_BOOTSTRAPS",
    "MIN_TIME_POINTS",
    "PROFILE_ID",
    "REQUIRED_ASSAY_COMPATIBILITY",
    "AnalysisSupport",
    "AssayCompatibilityAttestation",
    "DriverDirection",
    "HgncGeneSymbol",
    "LongitudinalAlgorithmConstants",
    "LongitudinalGbmProfile",
    "LongitudinalGbmProvenance",
    "LongitudinalGbmRequest",
    "LongitudinalGbmResult",
    "LongitudinalSourceModelCounts",
    "LongitudinalSourceModelDigests",
    "LongitudinalTimePoint",
    "NormalizationReference",
    "PeltAnalysis",
    "PeltBoundary",
    "ProteinEvidenceState",
    "ProteinObservation",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "SignedProteinDriver",
    "SourceProcessingAblation",
    "TopDriverAblation",
    "TransitionClassification",
    "TransitionEvidence",
    "TransitionUncertainty",
    "UncertaintyInteraction",
    "UncertaintyState",
    "UnverifiedLongitudinalGbmResult",
]
