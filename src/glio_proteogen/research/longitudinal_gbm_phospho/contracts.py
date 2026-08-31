"""Strict research contracts for source-locked longitudinal GBM phosphosites.

This lane applies only the frozen PDC000515 raw phosphosite transition axis.  It
does not estimate occupancy, fuse protein abundance, infer kinase activity, or
make diagnostic, prognostic, recurrence, or treatment claims.
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

ALGORITHM_ID = "kncc-gbm-longitudinal-phosphosite-concordance"
ALGORITHM_VERSION = "1.0.0"
ALGORITHM_PROFILE_ID = "kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"
PROFILE_ID = ALGORITHM_PROFILE_ID
MIN_TIME_POINTS = 2
MAX_TIME_POINTS = 16
MAX_OBSERVATIONS_PER_TIME_POINT = 4_096
MAX_TOTAL_OBSERVATIONS = 12_000
MIN_BOOTSTRAPS = 32
DEFAULT_BOOTSTRAPS = 64
MAX_BOOTSTRAPS = 64
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 4 * 1_024 * 1_024
MAX_REPLAY_BYTES = 8 * 1_024 * 1_024

PhosphositeId = Annotated[
    str,
    StringConstraints(
        min_length=8,
        max_length=64,
        pattern=r"^ENSP[0-9]+\.[0-9]+:[sty][0-9]+(?:[sty][0-9]+){0,2}$",
    ),
]
HgncGeneSymbol = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Za-z0-9._/-]*$"),
]


class PhosphositeEvidenceState(StrEnum):
    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class AnalysisSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class ModelViewSupport(StrEnum):
    FITTED = "fitted"
    NOT_FITTED = "not_fitted"


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
    """Exact, required compatibility statement for the PDC000515 fitted scale."""

    schema_version: Literal["glio-proteogen.kncc-phosphosite-assay-compatibility-attestation/1.0.0"]
    compatibility_profile_id: Literal["kncc-pdc000515-tmt11-phosphosite-log2-transition/1.0.0"]
    source_profile_digest: Literal[
        "sha256:81901f97d258f500dfc0aa31bf533e5bf45fa7d0e611820a58756e7ed8b64216"
    ]
    source_artifact_content_digest: Literal[
        "sha256:d31635cc2c9f634679ebd913cf2e0911b0bdff1fb66d53533239e870d4b8624a"
    ]
    assay: Literal["tmt11_plexed_phosphoproteome_mass_spectrometry"]
    quantification: Literal["phosphosite_sample_to_reference_abundance_ratio"]
    value_transformation: Literal["log2_ratio"]
    log_base: Literal[2]
    feature_identity: Literal["exact_ensp_versioned_source_site_group"]
    composite_site_policy: Literal["indivisible_source_site_group"]
    invariant_across_time_points: Literal[True]
    attested_compatible: Literal[True]


REQUIRED_ASSAY_COMPATIBILITY = AssayCompatibilityAttestation(
    schema_version="glio-proteogen.kncc-phosphosite-assay-compatibility-attestation/1.0.0",
    compatibility_profile_id="kncc-pdc000515-tmt11-phosphosite-log2-transition/1.0.0",
    source_profile_digest=(
        "sha256:81901f97d258f500dfc0aa31bf533e5bf45fa7d0e611820a58756e7ed8b64216"
    ),
    source_artifact_content_digest=(
        "sha256:d31635cc2c9f634679ebd913cf2e0911b0bdff1fb66d53533239e870d4b8624a"
    ),
    assay="tmt11_plexed_phosphoproteome_mass_spectrometry",
    quantification="phosphosite_sample_to_reference_abundance_ratio",
    value_transformation="log2_ratio",
    log_base=2,
    feature_identity="exact_ensp_versioned_source_site_group",
    composite_site_policy="indivisible_source_site_group",
    invariant_across_time_points=True,
    attested_compatible=True,
)


class NormalizationReference(FrozenModel):
    reference_id: Identifier
    binding_digest: Sha256Digest
    normalization_method: NonEmptyStr
    abundance_scale: Literal["caller_supplied_log2_phosphosite_abundance_ratio"] = (
        "caller_supplied_log2_phosphosite_abundance_ratio"
    )
    invariant_across_time_points: Literal[True] = True


class PhosphositeObservation(FrozenModel):
    observation_id: Identifier
    phosphosite_id: PhosphositeId
    gene_symbol: HgncGeneSymbol
    state: PhosphositeEvidenceState
    log_abundance_ratio: float | None = Field(default=None, ge=-100.0, le=100.0)
    standard_error: float | None = Field(default=None, gt=0.0, le=20.0)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_digest: Sha256Digest

    @model_validator(mode="after")
    def values_match_state(self) -> Self:
        active = self.state in {
            PhosphositeEvidenceState.OBSERVED,
            PhosphositeEvidenceState.LEFT_CENSORED,
        }
        if active and (self.log_abundance_ratio is None or self.standard_error is None):
            raise ValueError("active phosphosite evidence requires a value and standard error")
        if active and self.quality_weight <= 0.0:
            raise ValueError("active phosphosite evidence requires positive quality")
        if not active and (self.log_abundance_ratio is not None or self.standard_error is not None):
            raise ValueError("missing/unsupported evidence cannot carry numeric values")
        if not active and self.quality_weight != 0.0:
            raise ValueError("missing/unsupported evidence must have zero quality")
        return self


class LongitudinalPhosphoTimePoint(FrozenModel):
    time_point_id: Identifier
    time_offset_days: float = Field(ge=0.0)
    normalization_reference_digest: Sha256Digest
    observations: tuple[PhosphositeObservation, ...] = Field(
        min_length=1, max_length=MAX_OBSERVATIONS_PER_TIME_POINT
    )

    @field_validator("observations")
    @classmethod
    def observations_are_unique(
        cls, values: tuple[PhosphositeObservation, ...]
    ) -> tuple[PhosphositeObservation, ...]:
        ids = tuple(item.observation_id for item in values)
        sites = tuple(item.phosphosite_id for item in values)
        if len(ids) != len(set(ids)):
            raise ValueError(
                f"{cls.__name__} observation identifiers must be unique within a time point"
            )
        if len(sites) != len(set(sites)):
            raise ValueError("phosphosite identifiers must be unique within a time point")
        return values


class LongitudinalGbmPhosphoRequest(FrozenModel):
    profile_id: Literal["kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"
    )
    series_id: Identifier
    assay_compatibility: AssayCompatibilityAttestation
    normalization_reference: NormalizationReference
    time_points: tuple[LongitudinalPhosphoTimePoint, ...] = Field(
        min_length=MIN_TIME_POINTS, max_length=MAX_TIME_POINTS
    )
    bootstrap_replicates: int = Field(
        default=DEFAULT_BOOTSTRAPS, ge=MIN_BOOTSTRAPS, le=MAX_BOOTSTRAPS
    )

    @model_validator(mode="after")
    def series_is_ordered_and_bound(self) -> Self:
        ids = tuple(point.time_point_id for point in self.time_points)
        if len(ids) != len(set(ids)):
            raise ValueError("time-point identifiers must be unique")
        offsets = tuple(point.time_offset_days for point in self.time_points)
        if any(left >= right for left, right in pairwise(offsets)):
            raise ValueError("time offsets must be strictly increasing")
        digest = self.normalization_reference.binding_digest
        if any(point.normalization_reference_digest != digest for point in self.time_points):
            raise ValueError("every time point must bind the same normalization reference")
        observation_ids = tuple(
            item.observation_id for point in self.time_points for item in point.observations
        )
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation identifiers must be unique across the series")
        if len(observation_ids) > MAX_TOTAL_OBSERVATIONS:
            raise ValueError(f"requests are limited to {MAX_TOTAL_OBSERVATIONS} observations")
        return self

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class TransitionUncertainty(FrozenModel):
    state: UncertaintyState
    standard_error: float | None = Field(default=None, ge=0.0)
    variance: float | None = Field(default=None, ge=0.0)
    variance_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    bootstrap_replicates_used: int = Field(default=0, ge=0, le=MAX_BOOTSTRAPS)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def statistics_match_state(self) -> Self:
        if self.state is UncertaintyState.ESTIMATED:
            if (
                self.standard_error is None
                or self.variance is None
                or self.bootstrap_replicates_used == 0
            ):
                raise ValueError("estimated uncertainty requires bootstrap statistics")
            if self.reason is not None:
                raise ValueError("estimated uncertainty cannot carry a reason")
        elif (
            self.standard_error is not None
            or self.variance is not None
            or self.variance_fraction is not None
            or self.bootstrap_replicates_used != 0
            or self.reason is None
        ):
            raise ValueError("non-estimable uncertainty requires only a reason")
        return self


class UncertaintyInteraction(FrozenModel):
    state: UncertaintyState
    method: Literal["paired_full_model_bootstrap_interaction_decomposition_v1"] = (
        "paired_full_model_bootstrap_interaction_decomposition_v1"
    )
    interaction_standard_error: float | None = Field(default=None, ge=0.0)
    interaction_variance: float | None = Field(default=None, ge=0.0)
    interaction_variance_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    measurement_coefficient_covariance: float | None = None
    measurement_interaction_covariance: float | None = None
    coefficient_interaction_covariance: float | None = None
    variance_contribution: float | None = None
    combined_variance: float | None = Field(default=None, ge=0.0)
    decomposed_variance: float | None = Field(default=None, ge=0.0)
    decomposition_residual: float | None = None
    bootstrap_replicates_used: int = Field(default=0, ge=0, le=MAX_BOOTSTRAPS)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def statistics_match_state(self) -> Self:
        numeric = (
            self.interaction_standard_error,
            self.interaction_variance,
            self.interaction_variance_fraction,
            self.measurement_coefficient_covariance,
            self.measurement_interaction_covariance,
            self.coefficient_interaction_covariance,
            self.variance_contribution,
            self.combined_variance,
            self.decomposed_variance,
            self.decomposition_residual,
        )
        if self.state is UncertaintyState.ESTIMATED:
            if any(value is None for value in numeric) or self.bootstrap_replicates_used == 0:
                raise ValueError("estimated interaction requires covariance statistics")
            if self.reason is not None:
                raise ValueError("estimated interaction cannot carry a reason")
        elif any(value is not None for value in numeric) or self.bootstrap_replicates_used != 0:
            raise ValueError("non-estimable interaction cannot carry statistics")
        elif self.reason is None:
            raise ValueError("non-estimable interaction requires a reason")
        return self


class SignedPhosphositeDriver(FrozenModel):
    phosphosite_id: PhosphositeId
    gene_symbol: HgncGeneSymbol
    hgnc_id: NonEmptyStr
    site_cardinality: int = Field(ge=1, le=3)
    composite_site_group: bool
    from_observation_id: Identifier
    to_observation_id: Identifier
    from_provenance_digest: Sha256Digest
    to_provenance_digest: Sha256Digest
    value_semantics: Literal["exact_delta", "upper_bound", "lower_bound"]
    standardized_delta: float
    model_coefficient: float
    signed_contribution: float
    direction: DriverDirection
    reliability_weight: float = Field(gt=0.0, le=1.0)
    source_pair_support: int = Field(ge=1, le=88)
    bootstrap_selection_stability: float = Field(ge=0.0, le=1.0)
    sphinks_source_site_label: NonEmptyStr | None = None
    sphinks_signature_kinases: tuple[NonEmptyStr, ...] = Field(default=(), max_length=64)


class CensoredPhosphositeBound(FrozenModel):
    """A one-sided paired contrast retained without fabricating a point value."""

    phosphosite_id: PhosphositeId
    gene_symbol: HgncGeneSymbol
    value_semantics: Literal["upper_bound", "lower_bound"]
    standardized_bound: float
    coefficient_weighted_bound: float
    from_observation_id: Identifier
    to_observation_id: Identifier


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
                raise ValueError("abstained ablations cannot carry estimates")
            if self.classification_without_component is not TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("abstained ablations must be not estimable")
            if self.reason is None:
                raise ValueError("abstained ablations require a reason")
        else:
            if self.score_without_component is None or self.score_delta is None:
                raise ValueError("estimated ablations require scores")
            if self.classification_without_component is TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("estimated ablations cannot be not estimable")
            if self.support is AnalysisSupport.SUPPORTED and self.reason is not None:
                raise ValueError("supported ablations cannot carry a reason")
            if self.support is AnalysisSupport.LIMITED and self.reason is None:
                raise ValueError("limited ablations require a reason")
        return self


class FeatureFamilyAblation(_AblationEstimate):
    component: Literal["composite_site_groups", "exact_sphinks_crosswalk_sites"]
    omitted_feature_count: int = Field(ge=0, le=4_225)


class TopDriverAblation(_AblationEstimate):
    omitted_phosphosite_id: PhosphositeId
    omitted_signed_contribution: float


class ModelViewEvidence(FrozenModel):
    view: Literal["raw_phosphosite_transition", "occupancy_like", "protein_phosphosite_fusion"]
    support: ModelViewSupport
    reason: NonEmptyStr

    @model_validator(mode="after")
    def support_matches_view(self) -> Self:
        if (
            self.view == "raw_phosphosite_transition"
            and self.support is not ModelViewSupport.FITTED
        ):
            raise ValueError("the raw phosphosite transition view is the only fitted view")
        if (
            self.view != "raw_phosphosite_transition"
            and self.support is not ModelViewSupport.NOT_FITTED
        ):
            raise ValueError("occupancy-like and fusion views must remain not fitted")
        return self


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
    exact_feature_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    censored_feature_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    effective_sample_size: float = Field(ge=0.0)
    coefficient_weight_coverage: float = Field(ge=0.0, le=1.0)
    source_pair_coverage_weighted_mean: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Absolute-coefficient-weighted mean source-pair coverage among exactly paired "
            "fitted features; this is not a cohort percentile or rank."
        ),
    )
    measurement_uncertainty: TransitionUncertainty
    coefficient_uncertainty: TransitionUncertainty
    uncertainty_interaction: UncertaintyInteraction
    top_drivers: tuple[SignedPhosphositeDriver, ...] = Field(default=(), max_length=10)
    censored_bounds: tuple[CensoredPhosphositeBound, ...] = Field(default=(), max_length=4_225)
    feature_family_ablations: tuple[FeatureFamilyAblation, ...] = Field(default=(), max_length=2)
    top_driver_ablations: tuple[TopDriverAblation, ...] = Field(default=(), max_length=10)
    abstention_reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def interpretation_matches_support(self) -> Self:
        estimates = (self.score, self.lower_bound, self.upper_bound)
        if self.support is AnalysisSupport.ABSTAINED:
            if any(value is not None for value in estimates):
                raise ValueError("abstained transitions cannot carry estimates")
            if self.classification is not TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("abstained transitions must be not estimable")
            if self.bootstrap_replicates_used != 0 or not self.abstention_reasons:
                raise ValueError("abstained transitions require reasons and no bootstrap output")
        else:
            if any(value is None for value in estimates):
                raise ValueError("estimated transitions require a complete interval")
            score, lower, upper = (cast("float", value) for value in estimates)
            if not lower <= score <= upper:
                raise ValueError("transition interval must contain its score")
            if self.classification is TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("estimated transitions cannot be not estimable")
            if self.bootstrap_replicates_used == 0:
                raise ValueError("estimated transitions require bootstraps")
            if self.support is AnalysisSupport.SUPPORTED and self.abstention_reasons:
                raise ValueError("supported transitions cannot carry limitation reasons")
            if self.support is AnalysisSupport.LIMITED and not self.abstention_reasons:
                raise ValueError("limited transitions require a reason")
        return self


class SphinksCrosswalkProvenance(FrozenModel):
    source_name: Literal["SPHINKS"] = "SPHINKS"
    article_attribution: NonEmptyStr
    article_doi: Literal["10.1038/s43018-022-00510-x"] = "10.1038/s43018-022-00510-x"
    license: Literal["CC-BY-4.0"] = "CC-BY-4.0"
    license_url: Literal["https://creativecommons.org/licenses/by/4.0/"] = (
        "https://creativecommons.org/licenses/by/4.0/"
    )
    transformation_notice: NonEmptyStr
    runtime_use: Literal["exact_identity_annotation_only_no_kinase_inference"] = (
        "exact_identity_annotation_only_no_kinase_inference"
    )


class LongitudinalPhosphoProvenance(FrozenModel):
    engine: Literal["kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"
    )
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    source_artifact_content_digest: Sha256Digest
    source_artifact_byte_digest: Sha256Digest
    source_profile_digest: Sha256Digest
    source_manifest_digest: Sha256Digest
    source_attestation_state: Literal["verified_exact_snapshots"]
    bootstrap_ensemble_digest: Sha256Digest
    sphinks_crosswalk_digest: Sha256Digest
    hgnc_mapping_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    assay_compatibility_digest: Sha256Digest
    normalization_reference_digest: Sha256Digest
    computational_digest: Sha256Digest
    numerical_seed_digest: Sha256Digest
    bootstrap_seed: int = Field(ge=0, le=2**53 - 1)
    observation_source_digests: tuple[Sha256Digest, ...] = Field(max_length=MAX_TOTAL_OBSERVATIONS)
    numpy_version: NonEmptyStr
    source_attribution: NonEmptyStr
    source_license: NonEmptyStr
    source_license_url: NonEmptyStr
    source_transformation_notice: NonEmptyStr
    sphinks_crosswalk_provenance: SphinksCrosswalkProvenance


class _ResultDocument(FrozenModel):
    algorithm_id: Literal["kncc-gbm-longitudinal-phosphosite-concordance"] = (
        "kncc-gbm-longitudinal-phosphosite-concordance"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"
    )
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    series_id: Identifier
    assay_compatibility: AssayCompatibilityAttestation
    normalization_reference: NormalizationReference
    time_point_ids: tuple[Identifier, ...] = Field(
        min_length=MIN_TIME_POINTS, max_length=MAX_TIME_POINTS
    )
    transitions: tuple[TransitionEvidence, ...] = Field(
        min_length=MIN_TIME_POINTS - 1, max_length=MAX_TIME_POINTS - 1
    )
    model_views: tuple[ModelViewEvidence, ...] = Field(min_length=3, max_length=3)
    provenance: LongitudinalPhosphoProvenance
    output_semantics: Literal["raw_phosphosite_longitudinal_source_concordance"] = (
        "raw_phosphosite_longitudinal_source_concordance"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    infers_kinase_activity: Literal[False] = False

    @model_validator(mode="after")
    def topology_is_consistent(self) -> Self:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("profile digest does not match provenance")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("request digest does not match provenance")
        if (
            sha256_digest(self.assay_compatibility.model_dump(mode="json"))
            != self.provenance.assay_compatibility_digest
        ):
            raise ValueError("assay compatibility digest does not match provenance")
        if (
            self.normalization_reference.binding_digest
            != self.provenance.normalization_reference_digest
        ):
            raise ValueError("normalization reference digest does not match provenance")
        if len(self.transitions) != len(self.time_point_ids) - 1:
            raise ValueError("one transition is required per consecutive pair")
        for index, transition in enumerate(self.transitions):
            if transition.transition_index != index:
                raise ValueError("transition indices must be consecutive")
            if (
                transition.from_time_point_id != self.time_point_ids[index]
                or transition.to_time_point_id != self.time_point_ids[index + 1]
            ):
                raise ValueError("transition endpoints must match time-point order")
        expected_views = (
            "raw_phosphosite_transition",
            "occupancy_like",
            "protein_phosphosite_fusion",
        )
        if tuple(view.view for view in self.model_views) != expected_views:
            raise ValueError("all three model views must be explicit and ordered")
        return self


class LongitudinalGbmPhosphoResult(_ResultDocument):
    @model_validator(mode="after")
    def content_is_bound(self) -> Self:
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class UnverifiedLongitudinalGbmPhosphoResult(_ResultDocument):
    pass


class ReplayVerificationRequest(FrozenModel):
    request: LongitudinalGbmPhosphoRequest
    result: LongitudinalGbmPhosphoResult | UnverifiedLongitudinalGbmPhosphoResult


class ReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    transition_semantic_match: bool
    view_semantic_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr


class AlgorithmConstants(FrozenModel):
    transition_projection: Literal["frozen_sparse_l1_raw_delta_over_source_scale_v1"]
    missing_evidence_policy: Literal["missing_and_unsupported_never_become_negative_v1"]
    censoring_policy: Literal["one_sided_bounds_retained_but_excluded_from_point_projection_v1"]
    coefficient_uncertainty_policy: Literal[
        "exact_patient_bootstrap_full_huber_refit_replicate_scales_release_eligible_reselection_v2"
    ]
    measurement_uncertainty_policy: Literal[
        "deterministic_quality_scaled_gaussian_reported_value_perturbation_v1"
    ]
    measurement_covariance_policy: Literal[
        "featurewise_independent_gaussian_from_to_se_quadrature_no_shared_reference_covariance_v1"
    ]
    uncertainty_interaction_policy: Literal[
        "paired_full_model_bootstrap_interaction_decomposition_v1"
    ]
    composite_site_policy: Literal["source_site_groups_indivisible_v1"]
    minimum_exact_feature_fraction: float = Field(default=0.5, ge=0.5, le=0.5)
    minimum_coefficient_weight_coverage: float = Field(default=0.5, ge=0.5, le=0.5)
    alignment_threshold: float = Field(default=0.25, ge=0.25, le=0.25)
    stable_threshold: float = Field(default=0.05, ge=0.05, le=0.05)
    maximum_top_drivers: Literal[10] = 10
    default_bootstrap_replicates: Literal[64] = 64
    minimum_bootstrap_replicates: Literal[32] = 32
    maximum_bootstrap_replicates: Literal[64] = 64
    quantization_decimals: Literal[8] = 8


class SourceModelCounts(FrozenModel):
    source_feature_count: Literal[24_015] = 24_015
    eligible_feature_count: Literal[4_225] = 4_225
    selected_feature_count: int = Field(ge=1, le=4_225)
    strict_pair_count: Literal[88] = 88
    frozen_bootstrap_replicate_count: Literal[64] = 64
    exact_sphinks_crosswalk_feature_count: Literal[8_779] = 8_779
    sphinks_signature_feature_count: Literal[608] = 608


class SourceModelDigests(FrozenModel):
    source_artifact_content_digest: Sha256Digest
    source_artifact_byte_digest: Sha256Digest
    source_profile_digest: Sha256Digest
    source_manifest_digest: Sha256Digest
    bootstrap_ensemble_digest: Sha256Digest
    sphinks_crosswalk_digest: Sha256Digest
    hgnc_mapping_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest


class SourceModelQualityGates(FrozenModel):
    selection_stability_passed: bool
    bootstrap_full_refit_passed: bool
    bootstrap_feature_selection_stability_passed: bool
    bootstrap_calibration_passed: bool
    output_policy: Literal["unsupported_gate_forces_limited_or_abstained_v1"] = (
        "unsupported_gate_forces_limited_or_abstained_v1"
    )


class LongitudinalGbmPhosphoProfile(FrozenModel):
    algorithm_id: Literal["kncc-gbm-longitudinal-phosphosite-concordance"] = (
        "kncc-gbm-longitudinal-phosphosite-concordance"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-phosphosite-concordance/1.0.0"
    )
    model_id: Literal["kncc-paired-phosphosite-transition/1.0.0"] = (
        "kncc-paired-phosphosite-transition/1.0.0"
    )
    required_assay_compatibility: AssayCompatibilityAttestation
    constants: AlgorithmConstants
    counts: SourceModelCounts
    digests: SourceModelDigests
    quality_gates: SourceModelQualityGates
    numpy_version: NonEmptyStr
    demo_id: Identifier
    demo_request_digest: Sha256Digest
    demo_semantic_oracle_digest: Sha256Digest
    source_attribution: NonEmptyStr
    source_license: NonEmptyStr
    source_license_url: NonEmptyStr
    source_transformation_notice: NonEmptyStr
    sphinks_crosswalk_provenance: SphinksCrosswalkProvenance
    source_attestation_state: Literal["verified_exact_snapshots"]
    profile_digest: Sha256Digest
    safety_class: Literal["research_use_only"] = "research_use_only"
    claim_ceiling: Literal["raw_phosphosite_transition_concordance_only"] = (
        "raw_phosphosite_transition_concordance_only"
    )

    @model_validator(mode="after")
    def content_is_bound(self) -> Self:
        if self.profile_digest != profile_payload_digest(self):
            raise ValueError("profile digest does not match canonical profile content")
        return self


__all__ = [name for name in globals() if not name.startswith("_")]
