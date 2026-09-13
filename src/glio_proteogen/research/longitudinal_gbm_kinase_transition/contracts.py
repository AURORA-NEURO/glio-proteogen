"""Strict contracts for longitudinal SPHINKS signature-transition concordance.

This additive research lane never claims biochemical kinase activity, causal
regulation, recurrence prediction, or evidence independent of PDC000515.
"""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from glio_proteogen.research.longitudinal_gbm_phospho.contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    AssayCompatibilityAttestation,
    LongitudinalPhosphoTimePoint,
    NormalizationReference,
)

from .canonical import canonical_request_digest, profile_payload_digest, result_payload_digest

ALGORITHM_ID = "kncc-gbm-longitudinal-kinase-transition"
ALGORITHM_VERSION = "1.0.0"
ALGORITHM_PROFILE_ID = "kncc-gbm-longitudinal-kinase-transition/1.0.0"
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

KinaseSymbol = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9-]*$"),
]
SphinksSiteLabel = Annotated[str, StringConstraints(min_length=3, max_length=160)]


class AnalysisSupport(StrEnum):
    LIMITED = "limited"
    ABSTAINED = "abstained"


class SignatureDirection(StrEnum):
    SOURCE_RECURRENCE_ALIGNED = "source_recurrence_aligned"
    REVERSE_ALIGNED = "reverse_aligned"
    NOT_ESTABLISHED = "not_established"


class TransitionClassification(StrEnum):
    SOURCE_RECURRENCE_ALIGNED = "source_recurrence_aligned"
    REVERSE_ALIGNED = "reverse_aligned"
    STABLE = "stable"
    INDETERMINATE = "indeterminate"
    NOT_ESTIMABLE = "not_estimable"


class KinaseSelectionState(StrEnum):
    SELECTED_CORE = "selected_core"
    SELECTED_UNSTABLE = "selected_unstable"
    NOT_SELECTED = "not_selected"


class BootstrapState(StrEnum):
    ESTIMATED = "estimated"
    NOT_ESTIMABLE = "not_estimable"


class LongitudinalGbmKinaseTransitionRequest(FrozenModel):
    profile_id: Literal["kncc-gbm-longitudinal-kinase-transition/1.0.0"] = (
        "kncc-gbm-longitudinal-kinase-transition/1.0.0"
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
        if self.assay_compatibility != REQUIRED_ASSAY_COMPATIBILITY:
            raise ValueError("assay compatibility must exactly match the PDC000515 fitted scale")
        return self

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class BootstrapInterval(FrozenModel):
    state: BootstrapState
    lower_bound: float | None = None
    upper_bound: float | None = None
    standard_error: float | None = Field(default=None, ge=0.0)
    bootstrap_replicates_used: int = Field(default=0, ge=0, le=MAX_BOOTSTRAPS)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def interval_matches_state(self) -> Self:
        if self.state is BootstrapState.ESTIMATED:
            if (
                self.lower_bound is None
                or self.upper_bound is None
                or self.standard_error is None
                or self.bootstrap_replicates_used < MIN_BOOTSTRAPS
            ):
                raise ValueError("estimated bootstrap uncertainty requires a complete interval")
            if self.lower_bound > self.upper_bound or self.reason is not None:
                raise ValueError("estimated bootstrap interval is inconsistent")
        elif (
            self.lower_bound is not None
            or self.upper_bound is not None
            or self.standard_error is not None
            or self.bootstrap_replicates_used != 0
            or self.reason is None
        ):
            raise ValueError("non-estimable bootstrap uncertainty requires only a reason")
        return self


class SignatureFamilyDriver(FrozenModel):
    source_site_label: SphinksSiteLabel
    source_phosphosite_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    stratum: NonEmptyStr
    contains_composite_source_group: bool
    standardized_rank: float = Field(ge=-1.0, le=1.0)
    inverse_multiplicity: float = Field(gt=0.0, le=1.0)
    adjusted_source_weight: float = Field(gt=0.0)
    signed_contribution: float
    paired_source_support: int = Field(ge=53, le=88)
    paired_observation_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=32)
    observation_provenance_digests: tuple[Sha256Digest, ...] = Field(min_length=2, max_length=32)


class KinaseSignatureEvidence(FrozenModel):
    kinase: KinaseSymbol
    subtype: Literal["GPM", "MTC", "NEU", "PPR"]
    selection_state: KinaseSelectionState
    support: AnalysisSupport
    source_direction: SignatureDirection
    source_enrichment: float | None = None
    source_p_value: float = Field(ge=0.0, le=1.0)
    source_q_value: float = Field(ge=0.0, le=1.0)
    mapped_source_family_count: int = Field(ge=0, le=572)
    observed_family_count: int = Field(ge=0, le=572)
    source_weight_coverage: float = Field(ge=0.0, le=1.0)
    outer_selection_frequency: float = Field(ge=0.0, le=1.0)
    bootstrap_selection_frequency: float = Field(ge=0.0, le=1.0)
    bootstrap_direction_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    score: float | None = None
    classification: TransitionClassification
    uncertainty: BootstrapInterval
    top_family_drivers: tuple[SignatureFamilyDriver, ...] = Field(default=(), max_length=8)
    reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def evidence_matches_selection(self) -> Self:
        if self.selection_state is KinaseSelectionState.NOT_SELECTED:
            if self.support is not AnalysisSupport.ABSTAINED:
                raise ValueError("non-selected kinase hypotheses must abstain")
            if (
                self.score is not None
                or self.classification is not TransitionClassification.NOT_ESTIMABLE
            ):
                raise ValueError("non-selected kinase hypotheses cannot carry runtime estimates")
            if self.uncertainty.state is not BootstrapState.NOT_ESTIMABLE or not self.reasons:
                raise ValueError("non-selected kinase hypotheses require an abstention reason")
        elif self.support is AnalysisSupport.ABSTAINED:
            if (
                self.score is not None
                or self.classification is not TransitionClassification.NOT_ESTIMABLE
            ):
                raise ValueError("abstained selected kinase cannot carry an estimate")
            if self.uncertainty.state is not BootstrapState.NOT_ESTIMABLE or not self.reasons:
                raise ValueError("abstained selected kinase requires a reason")
        elif (
            self.score is None
            or self.classification is TransitionClassification.NOT_ESTIMABLE
            or self.uncertainty.state is not BootstrapState.ESTIMATED
            or not self.reasons
        ):
            raise ValueError("estimated kinase signature must remain explicitly limited")
        return self


class SubtypeSignatureEvidence(FrozenModel):
    subtype: Literal["GPM", "MTC", "NEU", "PPR"]
    selected_kinase_count: int = Field(ge=0, le=9)
    estimable_kinase_count: int = Field(ge=0, le=9)
    support: AnalysisSupport
    score: float | None = None
    classification: TransitionClassification
    uncertainty: BootstrapInterval
    reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def support_matches_estimate(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if (
                self.score is not None
                or self.classification is not TransitionClassification.NOT_ESTIMABLE
            ):
                raise ValueError("abstained subtype cannot carry an estimate")
            if self.uncertainty.state is not BootstrapState.NOT_ESTIMABLE or not self.reasons:
                raise ValueError("abstained subtype requires a reason")
        elif (
            self.score is None
            or self.classification is TransitionClassification.NOT_ESTIMABLE
            or self.uncertainty.state is not BootstrapState.ESTIMATED
            or not self.reasons
        ):
            raise ValueError("estimated subtype signature must remain explicitly limited")
        return self


class SignatureAblation(FrozenModel):
    ablation: Literal[
        "equal_kinase_instead_of_equal_subtype",
        "omit_composite_source_groups",
        "omit_inverse_multiplicity_correction",
    ]
    support: AnalysisSupport
    score: float | None = None
    score_delta: float | None = None
    classification: TransitionClassification
    reason: NonEmptyStr

    @model_validator(mode="after")
    def ablation_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if self.score is not None or self.score_delta is not None:
                raise ValueError("abstained ablation cannot carry an estimate")
            if self.classification is not TransitionClassification.NOT_ESTIMABLE:
                raise ValueError("abstained ablation must be not-estimable")
        elif self.score is None or self.score_delta is None:
            raise ValueError("limited ablation requires a score and delta")
        return self


class TransitionEvidence(FrozenModel):
    transition_id: Identifier
    transition_index: int = Field(ge=0, le=MAX_TIME_POINTS - 2)
    from_time_point_id: Identifier
    to_time_point_id: Identifier
    support: AnalysisSupport
    classification: TransitionClassification
    score: float | None = None
    uncertainty: BootstrapInterval
    exact_source_row_count: int = Field(ge=0, le=MAX_OBSERVATIONS_PER_TIME_POINT)
    exact_family_count: int = Field(ge=0, le=2_457)
    censored_family_count: int = Field(ge=0, le=2_457)
    selected_kinase_count: int = Field(ge=0, le=24)
    estimable_kinase_count: int = Field(ge=0, le=24)
    kinase_signatures: tuple[KinaseSignatureEvidence, ...] = Field(min_length=24, max_length=24)
    subtype_signatures: tuple[SubtypeSignatureEvidence, ...] = Field(min_length=4, max_length=4)
    ablations: tuple[SignatureAblation, ...] = Field(min_length=3, max_length=3)
    reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def transition_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if (
                self.score is not None
                or self.classification is not TransitionClassification.NOT_ESTIMABLE
            ):
                raise ValueError("abstained transition cannot carry an estimate")
            if self.uncertainty.state is not BootstrapState.NOT_ESTIMABLE or not self.reasons:
                raise ValueError("abstained transition requires a reason")
        elif (
            self.score is None
            or self.classification is TransitionClassification.NOT_ESTIMABLE
            or self.uncertainty.state is not BootstrapState.ESTIMATED
            or not self.reasons
        ):
            raise ValueError("estimated transition must remain explicitly limited")
        if tuple(item.kinase for item in self.kinase_signatures) != tuple(
            sorted(item.kinase for item in self.kinase_signatures)
        ):
            raise ValueError("kinase evidence must be sorted by exact HGNC symbol")
        if tuple(item.subtype for item in self.subtype_signatures) != ("GPM", "MTC", "NEU", "PPR"):
            raise ValueError("all four SPHINKS subtype families must be explicit and ordered")
        return self


class SourceModelCounts(FrozenModel):
    strict_patient_pairs: Literal[88] = 88
    exact_crosswalk_pdc_rows: Literal[8_779] = 8_779
    unique_crosswalk_families: Literal[8_533] = 8_533
    duplicate_family_extra_pdc_rows: Literal[246] = 246
    signature_pdc_rows: Literal[608] = 608
    unique_signature_families: Literal[572] = 572
    release_eligible_background_families: Literal[2_457] = 2_457
    fixed_master_kinase_hypotheses: Literal[24] = 24
    full_fit_selected_kinases: Literal[12] = 12
    core_stable_selected_kinases: Literal[11] = 11
    patient_bootstrap_replicates: Literal[64] = 64


class SourceModelDigests(FrozenModel):
    fitter_source_sha256: Sha256Digest
    fitted_artifact_content_digest: Sha256Digest
    fitted_artifact_byte_digest: Sha256Digest
    bootstrap_ensemble_digest: Sha256Digest
    pdc_phosphosite_artifact_content_digest: Sha256Digest
    pdc_phosphosite_source_profile_digest: Sha256Digest
    pdc_source_manifest_digest: Sha256Digest
    pdc_hgnc_mapping_digest: Sha256Digest
    pdc_sphinks_crosswalk_digest: Sha256Digest
    sphinks_catalog_artifact_digest: Sha256Digest
    sphinks_catalog_content_digest: Sha256Digest
    sphinks_background_tuple_digest: Sha256Digest
    sphinks_signature_edge_digest: Sha256Digest
    sphinks_master_kinase_digest: Sha256Digest
    sphinks_source_sha256: Sha256Digest
    engine_semantic_digest: Sha256Digest


class AlgorithmConstants(FrozenModel):
    hypothesis_family: Literal["fixed_24_sphinks_master_kinases_bh_v1"] = (
        "fixed_24_sphinks_master_kinases_bh_v1"
    )
    family_projection: Literal["residue_stratified_rank_concordance_v1"] = (
        "residue_stratified_rank_concordance_v1"
    )
    inverse_multiplicity_policy: Literal["global_selected_membership_inverse_count_v1"] = (
        "global_selected_membership_inverse_count_v1"
    )
    composite_site_policy: Literal["source_composite_groups_indivisible_v1"] = (
        "source_composite_groups_indivisible_v1"
    )
    missing_evidence_policy: Literal["missing_and_unsupported_never_become_negative_v1"] = (
        "missing_and_unsupported_never_become_negative_v1"
    )
    censoring_policy: Literal["one_sided_bounds_retained_excluded_from_point_score_v1"] = (
        "one_sided_bounds_retained_excluded_from_point_score_v1"
    )
    bootstrap_policy: Literal["exact_patient_refit_sparse_family_projection_v1"] = (
        "exact_patient_refit_sparse_family_projection_v1"
    )
    measurement_policy: Literal["deterministic_independent_gaussian_reported_se_v1"] = (
        "deterministic_independent_gaussian_reported_se_v1"
    )
    fdr_threshold: float = Field(default=0.1, ge=0.1, le=0.1)
    minimum_kinase_families: Literal[3] = 3
    minimum_source_weight_coverage: float = Field(default=0.25, ge=0.25, le=0.25)
    core_stability_threshold: float = Field(default=0.8, ge=0.8, le=0.8)
    alignment_threshold: float = Field(default=0.05, ge=0.05, le=0.05)
    maximum_top_drivers: Literal[8] = 8
    quantization_decimals: Literal[8] = 8


class SourceQualityGates(FrozenModel):
    same_assay_independent_evidence_gate_passed: Literal[False] = False
    patient_bootstrap_full_refit_convergence_gate_passed: Literal[True] = True
    patient_bootstrap_full_set_stability_gate_passed: Literal[False] = False
    patient_bootstrap_interval_calibration_gate_passed: Literal[False] = False
    output_policy: Literal["all_estimable_outputs_limited_otherwise_abstained"] = (
        "all_estimable_outputs_limited_otherwise_abstained"
    )


class SourceProvenance(FrozenModel):
    pdc_article_attribution: NonEmptyStr
    pdc_license: Literal["CC-BY-4.0"]
    pdc_license_url: Literal["https://creativecommons.org/licenses/by/4.0/"]
    pdc_transformation_notice: NonEmptyStr
    sphinks_article_attribution: NonEmptyStr
    sphinks_license: Literal["CC-BY-4.0"]
    sphinks_license_url: Literal["https://creativecommons.org/licenses/by/4.0/"]
    sphinks_transformation_notice: NonEmptyStr


class LongitudinalGbmKinaseTransitionProfile(FrozenModel):
    algorithm_id: Literal["kncc-gbm-longitudinal-kinase-transition"] = (
        "kncc-gbm-longitudinal-kinase-transition"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-gbm-longitudinal-kinase-transition/1.0.0"] = (
        "kncc-gbm-longitudinal-kinase-transition/1.0.0"
    )
    model_id: Literal["kncc-pdc000515-sphinks-signature-transition/1.0.0"]
    required_assay_compatibility: AssayCompatibilityAttestation
    constants: AlgorithmConstants
    counts: SourceModelCounts
    digests: SourceModelDigests
    quality_gates: SourceQualityGates
    source_provenance: SourceProvenance
    numpy_version: NonEmptyStr
    demo_id: NonEmptyStr
    demo_request_digest: Sha256Digest
    demo_semantic_oracle_digest: Sha256Digest
    source_attestation_state: Literal["verified_exact_snapshots"]
    safety_class: Literal["research_use_only"] = "research_use_only"
    claim_ceiling: Literal["SPHINKS_signature_transition_concordance_only"] = (
        "SPHINKS_signature_transition_concordance_only"
    )
    profile_digest: Sha256Digest

    @model_validator(mode="after")
    def content_is_bound(self) -> Self:
        if self.profile_digest != profile_payload_digest(self):
            raise ValueError("profile digest does not match canonical profile content")
        return self


class ResultProvenance(FrozenModel):
    engine: Literal["kncc-gbm-longitudinal-kinase-transition/1.0.0"] = (
        "kncc-gbm-longitudinal-kinase-transition/1.0.0"
    )
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    fitted_artifact_content_digest: Sha256Digest
    fitted_artifact_byte_digest: Sha256Digest
    bootstrap_ensemble_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    assay_compatibility_digest: Sha256Digest
    normalization_reference_digest: Sha256Digest
    computational_digest: Sha256Digest
    numerical_seed_digest: Sha256Digest
    observation_source_digests: tuple[Sha256Digest, ...] = Field(max_length=MAX_TOTAL_OBSERVATIONS)
    source_attestation_state: Literal["verified_exact_snapshots"]
    source_provenance: SourceProvenance
    numpy_version: NonEmptyStr


class _ResultDocument(FrozenModel):
    algorithm_id: Literal["kncc-gbm-longitudinal-kinase-transition"] = (
        "kncc-gbm-longitudinal-kinase-transition"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["kncc-gbm-longitudinal-kinase-transition/1.0.0"] = (
        "kncc-gbm-longitudinal-kinase-transition/1.0.0"
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
    provenance: ResultProvenance
    output_semantics: Literal["SPHINKS_signature_transition_concordance_only"] = (
        "SPHINKS_signature_transition_concordance_only"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    infers_kinase_activity: Literal[False] = False
    infers_biochemical_activity: Literal[False] = False
    makes_causal_claim: Literal[False] = False
    independent_evidence: Literal[False] = False

    @model_validator(mode="after")
    def topology_is_bound(self) -> Self:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("profile digest does not match provenance")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("request digest does not match provenance")
        if len(self.transitions) != len(self.time_point_ids) - 1:
            raise ValueError("one transition is required per consecutive time-point pair")
        for index, transition in enumerate(self.transitions):
            if transition.transition_index != index:
                raise ValueError("transition indices must be consecutive")
            if (
                transition.from_time_point_id != self.time_point_ids[index]
                or transition.to_time_point_id != self.time_point_ids[index + 1]
            ):
                raise ValueError("transition endpoints do not match the time-point topology")
        return self


class LongitudinalGbmKinaseTransitionResult(_ResultDocument):
    @model_validator(mode="after")
    def content_is_bound(self) -> Self:
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class UnverifiedLongitudinalGbmKinaseTransitionResult(_ResultDocument):
    pass


class ReplayVerificationRequest(FrozenModel):
    request: LongitudinalGbmKinaseTransitionRequest
    result: LongitudinalGbmKinaseTransitionResult | UnverifiedLongitudinalGbmKinaseTransitionResult


class ReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    transition_semantic_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr


__all__ = [name for name in globals() if not name.startswith("_")]
