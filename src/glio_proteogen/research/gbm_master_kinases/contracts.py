"""Strict research-only contracts for GBM master-kinase signature concordance.

These contracts describe independent GLIO-PROTEOGEN evidence concordance against
frozen SPHINKS/MK signatures.  They do not represent a SPHINKS port, retraining,
calibrated kinase activity, subtype probability, causality, or treatment guidance.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, StringConstraints, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .canonical import canonical_request_digest, result_payload_digest
from .catalog import independent_kinase_memberships_by_site, is_pinned_phosphosite

ALGORITHM_ID = "sphinks-gbm-master-kinase-concordance"
ALGORITHM_VERSION = "1.0.0"
ALGORITHM_PROFILE_ID = "sphinks-gbm-master-kinase-concordance/1.0.0"
PROFILE_ID = ALGORITHM_PROFILE_ID
MAX_OBSERVATIONS = 4_096
MAX_BOOTSTRAPS = 256
MAX_PERMUTATIONS = 2_048
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 2 * 1_024 * 1_024
MAX_REPLAY_BYTES = 4 * 1_024 * 1_024
LOCATION_SOLVER_ITERATIONS = 32
LOCATION_SEARCH_BOUND = 20.0
WORK_ACTIVE_OBSERVATION_BOOTSTRAP_WEIGHT = 2
WORK_OBSERVED_BACKGROUND_BOOTSTRAP_WEIGHT = 12
WORK_ACTIVE_MEMBERSHIP_BOOTSTRAP_WEIGHT = LOCATION_SOLVER_ITERATIONS
WORK_OBSERVED_MEMBERSHIP_BOOTSTRAP_WEIGHT = 2
WORK_OBSERVED_MEMBERSHIP_PERMUTATION_WEIGHT = 1
WORK_FIXED_HYPOTHESIS_PERMUTATION_OVERHEAD = 16 * 24
MAX_COMPUTATIONAL_WORK_UNITS = 14_000_000

PhosphositeId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/+()\-]*$",
        strip_whitespace=True,
    ),
]
ContrastLabel = Annotated[str, StringConstraints(min_length=1, max_length=256)]
KinaseSymbol = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9.-]*$"),
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


class StateClassification(StrEnum):
    ACTIVATED = "activated"
    SUPPRESSED = "suppressed"
    NEUTRAL = "neutral"
    INDETERMINATE = "indeterminate"
    NOT_ESTIMABLE = "not_estimable"


class MethodAgreement(StrEnum):
    CONCORDANT = "concordant"
    DISCORDANT = "discordant"
    UNCERTAIN = "uncertain"
    SINGLE_METHOD = "single_method"
    INSUFFICIENT = "insufficient"


class GbmSubtype(StrEnum):
    GPM = "GPM"
    MTC = "MTC"
    NEU = "NEU"
    PPR = "PPR"


class StandardizedContrastReference(FrozenModel):
    contrast_id: Identifier
    numerator_label: ContrastLabel
    denominator_label: ContrastLabel
    scale: Literal["caller_supplied_standardized_log2_contrast"] = (
        "caller_supplied_standardized_log2_contrast"
    )

    @model_validator(mode="after")
    def labels_are_distinct(self) -> Self:
        if self.numerator_label == self.denominator_label:
            raise ValueError("contrast numerator and denominator labels must differ")
        return self


class PhosphositeObservation(FrozenModel):
    observation_id: Identifier
    phosphosite_id: PhosphositeId
    state: PhosphositeEvidenceState
    standardized_effect: float | None = Field(
        default=None,
        ge=-20.0,
        le=20.0,
        description=("Point estimate when observed; upper detection limit when left_censored."),
    )
    standard_error: float | None = Field(
        default=None,
        gt=0.0,
        le=20.0,
        description=(
            "Point-estimate standard error when observed; uncertainty standard deviation "
            "of the reported upper limit when left_censored."
        ),
    )
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_digest: Sha256Digest

    @model_validator(mode="after")
    def numerical_values_match_state(self) -> Self:
        active = self.state in {
            PhosphositeEvidenceState.OBSERVED,
            PhosphositeEvidenceState.LEFT_CENSORED,
        }
        if active and (self.standardized_effect is None or self.standard_error is None):
            raise ValueError("observed and left-censored evidence require effect and error")
        if active and self.quality_weight <= 0.0:
            raise ValueError("active evidence requires positive quality")
        if not active and (self.standardized_effect is not None or self.standard_error is not None):
            raise ValueError("missing and unsupported evidence cannot carry numeric values")
        if not active and self.quality_weight != 0.0:
            raise ValueError("missing and unsupported evidence must have zero quality")
        return self


class MasterKinaseRequest(FrozenModel):
    profile_id: Literal["sphinks-gbm-master-kinase-concordance/1.0.0"] = (
        "sphinks-gbm-master-kinase-concordance/1.0.0"
    )
    sample_id: Identifier
    observations: tuple[PhosphositeObservation, ...] = Field(
        min_length=1,
        max_length=MAX_OBSERVATIONS,
    )
    bootstrap_replicates: int = Field(default=64, ge=16, le=MAX_BOOTSTRAPS)
    permutation_replicates: int = Field(default=256, ge=64, le=MAX_PERMUTATIONS)
    contrast_reference: StandardizedContrastReference
    background_mode: Literal["request_observed_pinned_table5a"] = "request_observed_pinned_table5a"

    @field_validator("observations")
    @classmethod
    def observations_are_unique_and_pinned(
        cls,
        values: tuple[PhosphositeObservation, ...],
    ) -> tuple[PhosphositeObservation, ...]:
        identifiers = tuple(item.observation_id for item in values)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{cls.__name__} observation identifiers must be unique")
        sites = tuple(item.phosphosite_id for item in values)
        if len(sites) != len(set(sites)):
            raise ValueError(f"{cls.__name__} exact phosphosite identifiers must be unique")
        invalid_active = sorted(
            item.phosphosite_id
            for item in values
            if item.state
            in {PhosphositeEvidenceState.OBSERVED, PhosphositeEvidenceState.LEFT_CENSORED}
            and not is_pinned_phosphosite(item.phosphosite_id)
        )
        if invalid_active:
            preview = ", ".join(invalid_active[:5])
            raise ValueError(
                "active evidence must exactly match the pinned Table 5a phosphosite-label "
                f"background; rejected: {preview}"
            )
        return values

    @model_validator(mode="after")
    def computational_work_is_bounded(self) -> Self:
        work_units = estimate_computational_work_units(
            self.observations,
            bootstrap_replicates=self.bootstrap_replicates,
            permutation_replicates=self.permutation_replicates,
        )
        if work_units > MAX_COMPUTATIONAL_WORK_UNITS:
            raise ValueError(
                "requested observation/replicate combination exceeds the deterministic "
                f"computational work budget ({work_units} > "
                f"{MAX_COMPUTATIONAL_WORK_UNITS} work units)"
            )
        return self

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)

    @property
    def estimated_work_units(self) -> int:
        """Return the profile-bound deterministic work estimate used at validation."""

        return estimate_computational_work_units(
            self.observations,
            bootstrap_replicates=self.bootstrap_replicates,
            permutation_replicates=self.permutation_replicates,
        )


def estimate_computational_work_units(
    observations: tuple[PhosphositeObservation, ...],
    *,
    bootstrap_replicates: int,
    permutation_replicates: int,
) -> int:
    """Estimate deterministic work from active/background/signature inventory.

    The result is a conservative operation-count proxy, not a wall-clock prediction.
    It prevents individually valid maxima from composing into a synchronous request
    that cannot meet the service execution budget.
    """

    memberships = independent_kinase_memberships_by_site()
    active = tuple(
        item
        for item in observations
        if item.state in {PhosphositeEvidenceState.OBSERVED, PhosphositeEvidenceState.LEFT_CENSORED}
    )
    observed = tuple(
        item for item in observations if item.state is PhosphositeEvidenceState.OBSERVED
    )
    active_memberships = sum(memberships.get(item.phosphosite_id, 0) for item in active)
    observed_memberships = sum(memberships.get(item.phosphosite_id, 0) for item in observed)
    bootstrap_units = bootstrap_replicates * (
        WORK_ACTIVE_OBSERVATION_BOOTSTRAP_WEIGHT * len(active)
        + WORK_OBSERVED_BACKGROUND_BOOTSTRAP_WEIGHT * len(observed)
        + WORK_ACTIVE_MEMBERSHIP_BOOTSTRAP_WEIGHT * active_memberships
        + WORK_OBSERVED_MEMBERSHIP_BOOTSTRAP_WEIGHT * observed_memberships
    )
    permutation_units = permutation_replicates * (
        WORK_OBSERVED_MEMBERSHIP_PERMUTATION_WEIGHT * observed_memberships
        + WORK_FIXED_HYPOTHESIS_PERMUTATION_OVERHEAD
    )
    return bootstrap_units + permutation_units


class MethodEstimate(FrozenModel):
    support: AnalysisSupport
    score: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    effective_sample_size: float = Field(ge=0.0)
    bootstrap_replicates_requested: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    bootstrap_replicates_successful: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    bootstrap_replicates_used: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def interval_matches_support(self) -> Self:
        numeric = (self.score, self.lower_bound, self.upper_bound)
        if not (
            self.bootstrap_replicates_used
            <= self.bootstrap_replicates_successful
            <= self.bootstrap_replicates_requested
        ):
            raise ValueError("bootstrap counts must satisfy used <= successful <= requested")
        if self.support is AnalysisSupport.ABSTAINED:
            if any(value is not None for value in numeric) or self.reason is None:
                raise ValueError("abstained methods require a reason and no estimate")
            if self.bootstrap_replicates_used != 0:
                raise ValueError("abstained methods cannot use bootstrap replicates")
        else:
            if any(value is None for value in numeric):
                raise ValueError("estimated methods require a complete interval")
            if self.bootstrap_replicates_requested == 0 or self.bootstrap_replicates_used == 0:
                raise ValueError(
                    "estimated methods require successful requested bootstrap replicates"
                )
            if self.bootstrap_replicates_used != self.bootstrap_replicates_successful:
                raise ValueError("estimated methods must use every successful bootstrap replicate")
            if self.support is AnalysisSupport.SUPPORTED and self.reason is not None:
                raise ValueError("supported methods cannot carry a limitation reason")
            if self.support is AnalysisSupport.LIMITED and self.reason is None:
                raise ValueError("limited methods require a reason")
            score = cast("float", self.score)
            lower = cast("float", self.lower_bound)
            upper = cast("float", self.upper_bound)
            if not lower <= score <= upper:
                raise ValueError("method interval must contain its score")
        return self


class RankEnrichmentEstimate(FrozenModel):
    support: AnalysisSupport
    score: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    effective_sample_size: float = Field(ge=0.0)
    bootstrap_replicates_requested: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    bootstrap_replicates_successful: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    bootstrap_replicates_used: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    mapped_signature_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)
    observed_background_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)
    permutation_replicates_used: int = Field(ge=0, le=MAX_PERMUTATIONS)
    null_standard_deviation: float | None = Field(default=None, ge=0.0)
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    q_value: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def statistics_match_support(self) -> Self:
        estimate = (self.score, self.lower_bound, self.upper_bound)
        statistics = (self.null_standard_deviation, self.p_value, self.q_value)
        if not (
            self.bootstrap_replicates_used
            <= self.bootstrap_replicates_successful
            <= self.bootstrap_replicates_requested
        ):
            raise ValueError("rank bootstrap counts must satisfy used <= successful <= requested")
        if self.support is AnalysisSupport.ABSTAINED:
            if any(value is not None for value in estimate + statistics) or self.reason is None:
                raise ValueError("abstained rank estimates require a reason and no statistics")
            if self.permutation_replicates_used != 0:
                raise ValueError("abstained rank estimates use zero permutations")
            if self.bootstrap_replicates_used != 0:
                raise ValueError("abstained rank estimates cannot use bootstrap replicates")
        else:
            if any(value is None for value in estimate + statistics):
                raise ValueError("estimated rank enrichment requires complete statistics")
            if self.bootstrap_replicates_requested == 0 or self.bootstrap_replicates_used == 0:
                raise ValueError(
                    "estimated rank enrichment requires successful requested bootstraps"
                )
            if self.bootstrap_replicates_used != self.bootstrap_replicates_successful:
                raise ValueError(
                    "estimated rank enrichment must use every successful bootstrap replicate"
                )
            if self.support is AnalysisSupport.SUPPORTED and self.reason is not None:
                raise ValueError("supported rank estimates cannot carry a reason")
            if self.support is AnalysisSupport.LIMITED and self.reason is None:
                raise ValueError("limited rank estimates require a reason")
            if (
                not cast("float", self.lower_bound)
                <= cast("float", self.score)
                <= cast("float", self.upper_bound)
            ):
                raise ValueError("rank interval must contain its score")
        return self


class SourceMasterKinaseReference(FrozenModel):
    kinase_activity_mww_score: float
    log2fc_activity_subtype_vs_others: float
    p_value: float = Field(ge=0.0, le=1.0)


class KinaseEvidenceCounts(FrozenModel):
    source_signature_edge_rows: int = Field(ge=1, le=MAX_OBSERVATIONS)
    signature_unique_sites: int = Field(ge=1, le=MAX_OBSERVATIONS)
    repeated_source_edge_rows: int = Field(ge=0, le=MAX_OBSERVATIONS)
    observed_signature_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)
    left_censored_signature_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)
    binding_left_censored_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)
    explicitly_missing_signature_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)
    unsupported_signature_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)
    unreported_signature_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)
    active_coverage: float = Field(ge=0.0, le=1.0)
    observed_background_sites: int = Field(ge=0, le=MAX_OBSERVATIONS)


class PhosphositeDriver(FrozenModel):
    observation_id: Identifier
    observation_provenance_digest: Sha256Digest
    phosphosite_id: PhosphositeId
    source_edge_row_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    evidence_state: PhosphositeEvidenceState
    value_role: Literal["observed_point", "left_censored_upper_limit"]
    standardized_effect: float
    source_svm_weight: float = Field(gt=0.0, le=1.0)
    reliability_weight: float = Field(gt=0.0)
    location_influence: float
    rank_influence: float | None = None


class EdgeAblation(FrozenModel):
    omitted_residue_stratum: NonEmptyStr
    source_edge_rows_removed: int = Field(ge=1, le=MAX_OBSERVATIONS)
    unique_sites_removed: int = Field(ge=1, le=MAX_OBSERVATIONS)
    location_delta: float | None = None
    rank_delta: float | None = None


class KinaseEvidence(FrozenModel):
    kinase_id: KinaseSymbol
    source_kinase_label: NonEmptyStr
    source_subtype: GbmSubtype
    support: AnalysisSupport
    classification: StateClassification
    source_reference: SourceMasterKinaseReference
    location: MethodEstimate
    rank_enrichment: RankEnrichmentEstimate
    method_agreement: MethodAgreement
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_counts: KinaseEvidenceCounts
    top_drivers: tuple[PhosphositeDriver, ...] = Field(default=(), max_length=5)
    edge_ablations: tuple[EdgeAblation, ...] = Field(default=(), max_length=7)
    abstention_reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def interpretation_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if self.classification is not StateClassification.NOT_ESTIMABLE:
                raise ValueError("abstained kinases must be not_estimable")
            if not self.abstention_reasons:
                raise ValueError("abstained kinases require reasons")
        elif self.classification is StateClassification.NOT_ESTIMABLE:
            raise ValueError("estimated kinases cannot be not_estimable")
        return self


class SubtypeKinaseDriver(FrozenModel):
    kinase_id: KinaseSymbol
    score: float
    aggregation_weight: float = Field(gt=0.0)
    influence: float


class SubtypeAblation(FrozenModel):
    omitted_kinase_id: KinaseSymbol
    subtype_score_delta: float | None = None


class SubtypeEvidence(FrozenModel):
    subtype_id: GbmSubtype
    support: AnalysisSupport
    classification: StateClassification
    aggregate: MethodEstimate
    member_kinases: tuple[KinaseSymbol, ...] = Field(min_length=1, max_length=9)
    supported_member_count: int = Field(ge=0, le=9)
    estimated_member_count: int = Field(ge=0, le=9)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    top_kinases: tuple[SubtypeKinaseDriver, ...] = Field(default=(), max_length=5)
    subtype_ablations: tuple[SubtypeAblation, ...] = Field(default=(), max_length=9)
    abstention_reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def interpretation_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if self.classification is not StateClassification.NOT_ESTIMABLE:
                raise ValueError("abstained subtypes must be not_estimable")
            if not self.abstention_reasons:
                raise ValueError("abstained subtypes require reasons")
        elif self.classification is StateClassification.NOT_ESTIMABLE:
            raise ValueError("estimated subtypes cannot be not_estimable")
        return self


class MasterKinaseProvenance(FrozenModel):
    engine: Literal["sphinks-gbm-master-kinase-concordance/1.0.0"] = (
        "sphinks-gbm-master-kinase-concordance/1.0.0"
    )
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    catalog_content_digest: Sha256Digest
    catalog_artifact_digest: Sha256Digest
    source_workbook_digest: Sha256Digest
    table5a_background_tuple_digest: Sha256Digest
    table5a_background_label_digest: Sha256Digest
    table5d_signature_edge_digest: Sha256Digest
    table5e_master_kinase_digest: Sha256Digest
    kinase_alias_digest: Sha256Digest
    engine_source_digest: Sha256Digest
    demo_result_oracle_digest: Sha256Digest
    numpy_version: NonEmptyStr
    computational_digest: Sha256Digest
    bootstrap_seed: int = Field(ge=0, le=2**53 - 1)
    permutation_seed: int = Field(ge=0, le=2**53 - 1)
    bootstrap_replicates_requested: int = Field(ge=16, le=MAX_BOOTSTRAPS)
    permutation_replicates_requested: int = Field(ge=64, le=MAX_PERMUTATIONS)
    observation_source_digests: tuple[Sha256Digest, ...] = Field(max_length=MAX_OBSERVATIONS)
    source_article_doi: NonEmptyStr
    source_article_title: NonEmptyStr
    source_article_authors: NonEmptyStr
    source_url: NonEmptyStr
    source_license: Literal["CC-BY-4.0"] = "CC-BY-4.0"
    source_license_url: Literal["https://creativecommons.org/licenses/by/4.0/"] = (
        "https://creativecommons.org/licenses/by/4.0/"
    )
    source_transformation_notice: NonEmptyStr


class MasterKinaseResult(FrozenModel):
    algorithm_id: Literal["sphinks-gbm-master-kinase-concordance"] = (
        "sphinks-gbm-master-kinase-concordance"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["sphinks-gbm-master-kinase-concordance/1.0.0"] = (
        "sphinks-gbm-master-kinase-concordance/1.0.0"
    )
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    contrast_reference: StandardizedContrastReference
    kinase_evidence: tuple[KinaseEvidence, ...] = Field(min_length=24, max_length=24)
    subtype_evidence: tuple[SubtypeEvidence, ...] = Field(min_length=4, max_length=4)
    provenance: MasterKinaseProvenance
    output_semantics: Literal["independent_signature_concordance_evidence"] = (
        "independent_signature_concordance_evidence"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=12)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def result_is_content_bound(self) -> Self:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("profile digest does not match provenance")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("request digest does not match provenance")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        kinase_ids = tuple(item.kinase_id for item in self.kinase_evidence)
        if len(kinase_ids) != len(set(kinase_ids)):
            raise ValueError("kinase result identifiers must be unique")
        subtype_ids = tuple(item.subtype_id for item in self.subtype_evidence)
        if len(subtype_ids) != len(set(subtype_ids)):
            raise ValueError("subtype result identifiers must be unique")
        return self


class UnverifiedMasterKinaseResult(FrozenModel):
    algorithm_id: Literal["sphinks-gbm-master-kinase-concordance"] = (
        "sphinks-gbm-master-kinase-concordance"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["sphinks-gbm-master-kinase-concordance/1.0.0"] = (
        "sphinks-gbm-master-kinase-concordance/1.0.0"
    )
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    contrast_reference: StandardizedContrastReference
    kinase_evidence: tuple[KinaseEvidence, ...] = Field(min_length=24, max_length=24)
    subtype_evidence: tuple[SubtypeEvidence, ...] = Field(min_length=4, max_length=4)
    provenance: MasterKinaseProvenance
    output_semantics: Literal["independent_signature_concordance_evidence"] = (
        "independent_signature_concordance_evidence"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=12)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True


class ReplayVerificationRequest(FrozenModel):
    request: MasterKinaseRequest
    result: MasterKinaseResult | UnverifiedMasterKinaseResult


class ReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr


class MasterKinaseAlgorithmConstants(FrozenModel):
    location_estimator: Literal["collapsed_site_one_sided_huber_bisection_v2"]
    duplicate_edge_policy: Literal["mean_svm_probability_per_kinase_site_v1"]
    rank_estimator: Literal["residue_stratified_competitive_weighted_rank_v2"]
    bootstrap_policy: Literal["request_digest_seeded_normal_and_symmetric_limit_v2"]
    subtype_pooling_policy: Literal["robust_source_mww_weighted_complete_tracks_v2"]
    rank_null_policy: Literal[
        "two_sided_residue_stratified_observation_tuple_permutation_fixed24_bh_v2"
    ]
    work_budget_policy: Literal["active_background_membership_replicate_units_v1"]
    huber_delta: float = Field(gt=0.0)
    standard_error_floor: float = Field(gt=0.0)
    location_ridge: float = Field(gt=0.0)
    location_solver_iterations: int = Field(ge=16, le=128)
    location_search_bound: float = Field(gt=0.0, le=100.0)
    activation_threshold: float = Field(gt=0.0)
    minimum_location_sites: int = Field(gt=0)
    supported_minimum_sites: int = Field(gt=0)
    supported_minimum_observed_sites: int = Field(gt=0)
    supported_minimum_coverage: float = Field(gt=0.0, le=1.0)
    supported_minimum_effective_sample_size: float = Field(gt=0.0)
    minimum_rank_signature_sites: int = Field(gt=0)
    minimum_rank_background: int = Field(gt=0)
    supported_minimum_rank_background: int = Field(gt=0)
    minimum_residue_stratum_competitors: int = Field(gt=0)
    rank_q_threshold: float = Field(gt=0.0, le=1.0)
    interval_lower_quantile: float = Field(ge=0.0, lt=0.5)
    interval_upper_quantile: float = Field(gt=0.5, le=1.0)
    minimum_bootstrap_success_fraction: float = Field(gt=0.5, le=1.0)
    quantization_decimals: int = Field(ge=0, le=15)
    random_seed_bytes: int = Field(ge=4, le=32)
    default_bootstrap_replicates: int = Field(ge=16, le=MAX_BOOTSTRAPS)
    default_permutation_replicates: int = Field(ge=64, le=MAX_PERMUTATIONS)
    subtype_minimum_estimated_kinases: int = Field(gt=0)
    subtype_minimum_estimated_fraction: float = Field(gt=0.0, le=1.0)
    subtype_minimum_supported_kinases: int = Field(gt=0)
    max_computational_work_units: int = Field(gt=0)
    work_active_observation_bootstrap_weight: int = Field(gt=0)
    work_observed_background_bootstrap_weight: int = Field(gt=0)
    work_active_membership_bootstrap_weight: int = Field(gt=0)
    work_observed_membership_bootstrap_weight: int = Field(gt=0)
    work_observed_membership_permutation_weight: int = Field(gt=0)
    work_fixed_hypothesis_permutation_overhead: int = Field(gt=0)


class MasterKinaseProfile(FrozenModel):
    algorithm_id: Literal["sphinks-gbm-master-kinase-concordance"] = (
        "sphinks-gbm-master-kinase-concordance"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["sphinks-gbm-master-kinase-concordance/1.0.0"] = (
        "sphinks-gbm-master-kinase-concordance/1.0.0"
    )
    constants: MasterKinaseAlgorithmConstants
    numpy_version: NonEmptyStr
    catalog_content_digest: Sha256Digest
    catalog_artifact_digest: Sha256Digest
    source_workbook_digest: Sha256Digest
    table5a_background_tuple_digest: Sha256Digest
    table5a_background_label_digest: Sha256Digest
    table5d_signature_edge_digest: Sha256Digest
    table5e_master_kinase_digest: Sha256Digest
    kinase_alias_digest: Sha256Digest
    engine_source_digest: Sha256Digest
    demo_id: Identifier
    demo_request_digest: Sha256Digest
    demo_result_oracle_digest: Sha256Digest
    source_attribution: NonEmptyStr
    source_license: Literal["CC-BY-4.0"] = "CC-BY-4.0"
    source_license_url: Literal["https://creativecommons.org/licenses/by/4.0/"] = (
        "https://creativecommons.org/licenses/by/4.0/"
    )
    source_transformation_notice: NonEmptyStr
    profile_digest: Sha256Digest
    safety_class: Literal["research_use_only"] = "research_use_only"
    interpretation: Literal["independent_signature_concordance_non_prescriptive"] = (
        "independent_signature_concordance_non_prescriptive"
    )


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_PROFILE_ID",
    "ALGORITHM_VERSION",
    "MAX_BOOTSTRAPS",
    "MAX_COMPUTATIONAL_WORK_UNITS",
    "MAX_OBSERVATIONS",
    "MAX_PERMUTATIONS",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "PROFILE_ID",
    "AnalysisSupport",
    "EdgeAblation",
    "GbmSubtype",
    "KinaseEvidence",
    "KinaseEvidenceCounts",
    "MasterKinaseAlgorithmConstants",
    "MasterKinaseProfile",
    "MasterKinaseProvenance",
    "MasterKinaseRequest",
    "MasterKinaseResult",
    "MethodAgreement",
    "MethodEstimate",
    "PhosphositeDriver",
    "PhosphositeEvidenceState",
    "PhosphositeObservation",
    "RankEnrichmentEstimate",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "SourceMasterKinaseReference",
    "StandardizedContrastReference",
    "StateClassification",
    "SubtypeAblation",
    "SubtypeEvidence",
    "SubtypeKinaseDriver",
    "UnverifiedMasterKinaseResult",
    "estimate_computational_work_units",
]
