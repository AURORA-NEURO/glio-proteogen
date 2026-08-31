"""Strict research contracts for published GBM proteomic signature models.

The contracts expose a content-bound, non-clinical wrapper around the published
Diamandis-lab GBM proteomic XGBoost models.  They do not reinterpret absent model
features as biological absence and do not modify any governed v1 contract.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, StringConstraints, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .canonical import request_digest, result_digest

ALGORITHM_ID = "gbm-proteomic-axes"
ALGORITHM_VERSION = "1.0.0"
PROFILE_ID = "gbm-proteomic-axes/1.0.0"

MAX_MEASUREMENTS = 8_192
MAX_SIGNATURES = 7
MAX_BOOTSTRAPS = 256
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 1 * 1_024 * 1_024
MAX_REPLAY_BYTES = 4 * 1_024 * 1_024
MAX_TOP_DRIVERS = 10
MAX_JSON_SAFE_INTEGER = 2**53 - 1

MIN_OBSERVED_MODEL_FEATURES = 32
SUPPORTED_COVERAGE_FRACTION = 0.50

SUPPORTED_SIGNATURE_IDS: tuple[str, ...] = (
    "SWEET_KRAS_TARGETS_UP",
    "HALLMARK_MYC_TARGETS_V1",
    "WINTER_HYPOXIA_UP",
    "VERHAAK_GLIOBLASTOMA_MESENCHYMAL",
    "VERHAAK_GLIOBLASTOMA_NEURAL",
    "VERHAAK_GLIOBLASTOMA_PRONEURAL",
    "EGFR_UP.V1_UP",
)

GeneSymbol = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9.-]*$"),
]
HttpsUrl = Annotated[
    str,
    StringConstraints(max_length=512, pattern=r"^https://[^\s]+$"),
]


class GbmProteinEvidenceState(StrEnum):
    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class GbmSignatureSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class GbmProteinMeasurement(FrozenModel):
    """One canonical-gene LFQ declaration with explicit absence semantics."""

    gene_symbol: GeneSymbol
    state: GbmProteinEvidenceState
    lfq_intensity: float | None = Field(default=None, gt=0.0, le=1.0e18)
    lfq_upper_limit: float | None = Field(default=None, gt=0.0, le=1.0e18)
    log2_standard_error: float | None = Field(default=None, gt=0.0, le=4.0)
    provenance_digest: Sha256Digest

    @model_validator(mode="after")
    def values_match_state(self) -> Self:
        if self.state is GbmProteinEvidenceState.OBSERVED:
            if self.lfq_intensity is None or self.lfq_upper_limit is not None:
                raise ValueError("observed evidence requires LFQ intensity and no upper limit")
            return self
        if self.state is GbmProteinEvidenceState.LEFT_CENSORED:
            if self.lfq_upper_limit is None or self.lfq_intensity is not None:
                raise ValueError("left-censored evidence requires an LFQ upper limit only")
            if self.log2_standard_error is not None:
                raise ValueError("left-censored evidence cannot use symmetric standard error")
            return self
        if any(
            value is not None
            for value in (self.lfq_intensity, self.lfq_upper_limit, self.log2_standard_error)
        ):
            raise ValueError("missing and unsupported evidence cannot carry numeric LFQ values")
        return self


class GbmProteomicAxesRequest(FrozenModel):
    profile_id: Literal["gbm-proteomic-axes/1.0.0"] = "gbm-proteomic-axes/1.0.0"
    sample_id: Identifier
    measurements: tuple[GbmProteinMeasurement, ...] = Field(
        min_length=1, max_length=MAX_MEASUREMENTS
    )
    signature_ids: tuple[Identifier, ...] = Field(default=(), max_length=MAX_SIGNATURES)
    bootstrap_replicates: int = Field(default=64, ge=0, le=MAX_BOOTSTRAPS)

    @field_validator("measurements")
    @classmethod
    def gene_symbols_are_unique(
        cls, values: tuple[GbmProteinMeasurement, ...]
    ) -> tuple[GbmProteinMeasurement, ...]:
        symbols = tuple(item.gene_symbol for item in values)
        if len(symbols) != len(set(symbols)):
            raise ValueError("gene symbols must be unique")
        return values

    @field_validator("signature_ids")
    @classmethod
    def signatures_are_supported_and_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("signature identifiers must be unique")
        unknown = set(values).difference(SUPPORTED_SIGNATURE_IDS)
        if unknown:
            raise ValueError("request contains an unsupported signature identifier")
        return values

    @field_validator("bootstrap_replicates")
    @classmethod
    def bootstrap_count_is_zero_or_evaluable(cls, value: int) -> int:
        if 0 < value < 8:
            raise ValueError("bootstrap replicates must be zero or at least eight")
        return value

    @property
    def request_digest(self) -> str:
        return request_digest(self)


class GbmNormalizationSummary(FrozenModel):
    method: Literal["positive_lfq_geometric_mean_to_1e7"] = (
        "positive_lfq_geometric_mean_to_1e7"
    )
    geometric_mean: float | None = Field(default=None, gt=0.0)
    normalization_factor: float | None = Field(default=None, gt=0.0)
    positive_input_proteins: int = Field(ge=0, le=MAX_MEASUREMENTS)

    @model_validator(mode="after")
    def values_exist_together(self) -> Self:
        values = (self.geometric_mean, self.normalization_factor)
        if self.positive_input_proteins == 0 and any(item is not None for item in values):
            raise ValueError("empty normalization cannot carry geometric-mean values")
        if self.positive_input_proteins > 0 and any(item is None for item in values):
            raise ValueError("positive LFQ input requires complete normalization values")
        return self


class GbmEvidenceSummary(FrozenModel):
    total_measurements: int = Field(ge=1, le=MAX_MEASUREMENTS)
    observed: int = Field(ge=0, le=MAX_MEASUREMENTS)
    left_censored: int = Field(ge=0, le=MAX_MEASUREMENTS)
    missing: int = Field(ge=0, le=MAX_MEASUREMENTS)
    unsupported: int = Field(ge=0, le=MAX_MEASUREMENTS)
    observed_model_features: int = Field(ge=0, le=MAX_MEASUREMENTS)
    observed_non_model_features: int = Field(ge=0, le=MAX_MEASUREMENTS)
    observations_with_standard_error: int = Field(ge=0, le=MAX_MEASUREMENTS)
    left_censored_point_policy: Literal["excluded_from_point_prediction"] = (
        "excluded_from_point_prediction"
    )
    absent_feature_semantics: Literal["published_zero_fill_not_biological_absence"] = (
        "published_zero_fill_not_biological_absence"
    )

    @model_validator(mode="after")
    def counts_reconcile(self) -> Self:
        state_total = self.observed + self.left_censored + self.missing + self.unsupported
        if state_total != self.total_measurements:
            raise ValueError("evidence-state counts must equal total measurements")
        if self.observed_model_features + self.observed_non_model_features != self.observed:
            raise ValueError("observed model and non-model counts must equal observations")
        if self.observations_with_standard_error > self.observed:
            raise ValueError("standard-error count cannot exceed observations")
        return self


class GbmFeatureDriver(FrozenModel):
    gene_symbol: GeneSymbol
    signed_contribution: float
    absolute_contribution: float = Field(ge=0.0)
    declared_state: GbmProteinEvidenceState | None = None
    model_input_source: Literal["observed_lfq", "published_zero_fill"]
    contribution_semantics: Literal["summed_tree_path_not_causal_or_shap"] = (
        "summed_tree_path_not_causal_or_shap"
    )

    @model_validator(mode="after")
    def magnitude_matches_signed_contribution(self) -> Self:
        if not math.isclose(
            self.absolute_contribution,
            abs(self.signed_contribution),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("driver magnitude must equal its absolute contribution")
        return self


class GbmSignatureEstimate(FrozenModel):
    signature_id: Identifier
    display_name: NonEmptyStr
    support: GbmSignatureSupport
    published_score: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    model_intercept: float | None = None
    model_feature_count: int = Field(gt=0)
    observed_feature_count: int = Field(ge=0)
    observed_feature_fraction: float = Field(ge=0.0, le=1.0)
    missing_feature_count: int = Field(ge=0)
    missing_feature_ratio: float = Field(ge=0.0, le=1.0)
    bootstrap_replicates_used: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    top_feature_drivers: tuple[GbmFeatureDriver, ...] = Field(
        default=(), max_length=MAX_TOP_DRIVERS
    )
    abstention_reason: NonEmptyStr | None = None
    zero_fill_convention: Literal[
        "unmeasured_model_features_set_to_numeric_zero_by_published_model"
    ] = "unmeasured_model_features_set_to_numeric_zero_by_published_model"

    @model_validator(mode="after")
    def support_and_estimate_are_coherent(self) -> Self:
        if self.observed_feature_count + self.missing_feature_count != self.model_feature_count:
            raise ValueError("observed and missing model features must reconcile")
        expected_observed_fraction = self.observed_feature_count / self.model_feature_count
        expected_missing_ratio = self.missing_feature_count / self.model_feature_count
        if not math.isclose(
            self.observed_feature_fraction,
            expected_observed_fraction,
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.missing_feature_ratio,
            expected_missing_ratio,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("signature coverage fractions must match feature counts")
        estimate = (self.published_score, self.model_intercept)
        interval = (self.lower_bound, self.upper_bound)
        if self.support is GbmSignatureSupport.ABSTAINED:
            if any(item is not None for item in (*estimate, *interval)):
                raise ValueError("abstained signatures cannot carry scores or intervals")
            if self.abstention_reason is None:
                raise ValueError("abstained signatures require a reason")
            if self.bootstrap_replicates_used != 0 or self.top_feature_drivers:
                raise ValueError("abstained signatures cannot carry bootstrap or driver claims")
            return self
        if any(item is None for item in estimate):
            raise ValueError("estimated signatures require published score and model intercept")
        if self.abstention_reason is not None:
            raise ValueError("estimated signatures cannot carry an abstention reason")
        if (self.lower_bound is None) != (self.upper_bound is None):
            raise ValueError("bootstrap interval bounds must be supplied together")
        if self.bootstrap_replicates_used == 0 and any(item is not None for item in interval):
            raise ValueError("an interval requires bootstrap replicates")
        if self.bootstrap_replicates_used > 0:
            if any(item is None for item in interval):
                raise ValueError("bootstrap replicates require an interval")
            score = cast("float", self.published_score)
            lower = cast("float", self.lower_bound)
            upper = cast("float", self.upper_bound)
            if not lower <= score <= upper:
                raise ValueError("bootstrap interval must contain the published score")
        return self


class GbmProteomicAxesProvenance(FrozenModel):
    engine: Literal["gbm-proteomic-axes/1.0.0"] = "gbm-proteomic-axes/1.0.0"
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    computational_digest: Sha256Digest
    deterministic_seed: int = Field(ge=0, le=MAX_JSON_SAFE_INTEGER)
    numpy_version: NonEmptyStr
    source_repository_url: HttpsUrl
    source_commit: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    original_model_digest: Sha256Digest
    converted_artifact_digest: Sha256Digest
    observation_source_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1, max_length=MAX_MEASUREMENTS
    )


class GbmProteomicAxesResult(FrozenModel):
    algorithm_id: Literal["gbm-proteomic-axes"] = "gbm-proteomic-axes"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["gbm-proteomic-axes/1.0.0"] = "gbm-proteomic-axes/1.0.0"
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    normalization: GbmNormalizationSummary
    evidence: GbmEvidenceSummary
    signatures: tuple[GbmSignatureEstimate, ...] = Field(
        min_length=1, max_length=MAX_SIGNATURES
    )
    provenance: GbmProteomicAxesProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def receipt_is_content_bound(self) -> Self:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("provenance profile digest does not match result")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("provenance request digest does not match result")
        identifiers = tuple(item.signature_id for item in self.signatures)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("result signature identifiers must be unique")
        if self.result_digest != result_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class UnverifiedGbmProteomicAxesResult(FrozenModel):
    """Structurally valid caller receipt accepted before integrity verification."""

    algorithm_id: Literal["gbm-proteomic-axes"] = "gbm-proteomic-axes"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["gbm-proteomic-axes/1.0.0"] = "gbm-proteomic-axes/1.0.0"
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    normalization: GbmNormalizationSummary
    evidence: GbmEvidenceSummary
    signatures: tuple[GbmSignatureEstimate, ...] = Field(
        min_length=1, max_length=MAX_SIGNATURES
    )
    provenance: GbmProteomicAxesProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True


class GbmReplayVerificationRequest(FrozenModel):
    request: GbmProteomicAxesRequest
    result: GbmProteomicAxesResult | UnverifiedGbmProteomicAxesResult


class GbmReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    model_source_match: bool
    result_digest_match: bool
    semantic_match: bool
    provided_result_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    recomputed_request_digest: Sha256Digest
    message: NonEmptyStr


class GbmProteomicAxesConstants(FrozenModel):
    normalization_method: Literal["positive_lfq_geometric_mean_to_1e7"]
    normalization_target: Literal[10000000] = 10_000_000
    missing_feature_policy: Literal["published_numeric_zero_fill"]
    missing_feature_interpretation: Literal["not_biological_absence"]
    left_censored_point_policy: Literal["excluded_from_point_prediction"]
    published_output_offset: Literal[10] = 10
    published_score_decimals: Literal[4] = 4
    minimum_observed_model_features: Literal[32] = 32
    supported_coverage_fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    bootstrap_sampling_policy: Literal["observed_lfq_log2_normal_v1"]
    bootstrap_interval_lower_quantile: float = Field(default=0.05, ge=0.0, lt=0.5)
    bootstrap_interval_upper_quantile: float = Field(default=0.95, gt=0.5, le=1.0)
    bootstrap_log2_minimum: Literal[-30] = -30
    bootstrap_log2_maximum: Literal[60] = 60
    random_seed_bytes: Literal[8] = 8
    random_seed_modulus: Literal[9007199254740992] = 9_007_199_254_740_992
    top_driver_limit: Literal[10] = 10


class GbmProteomicAxesLimits(FrozenModel):
    max_measurements: Literal[8192] = 8_192
    max_signatures: Literal[7] = 7
    max_bootstrap_replicates: Literal[256] = 256
    max_request_bytes: Literal[2097152] = 2_097_152
    max_result_bytes: Literal[1048576] = 1_048_576
    max_replay_bytes: Literal[4194304] = 4_194_304


class GbmSignatureProfile(FrozenModel):
    signature_id: Identifier
    display_name: NonEmptyStr
    role: Literal["triple_axis", "gbm_reference_program", "egfr_program"]
    model_feature_count: Literal[3025] = 3_025
    boosting_rounds: Literal[600] = 600


class GbmModelSource(FrozenModel):
    paper_title: NonEmptyStr
    paper_doi: Literal["10.1038/s41467-021-27667-w"] = "10.1038/s41467-021-27667-w"
    paper_url: HttpsUrl
    repository_url: HttpsUrl
    repository_commit: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    repository_license: Literal["MIT"] = "MIT"
    original_model_digest: Sha256Digest
    converted_artifact_digest: Sha256Digest
    conversion_note: NonEmptyStr


class GbmProteomicAxesProfile(FrozenModel):
    algorithm_id: Literal["gbm-proteomic-axes"] = "gbm-proteomic-axes"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["gbm-proteomic-axes/1.0.0"] = "gbm-proteomic-axes/1.0.0"
    numpy_version: NonEmptyStr
    constants: GbmProteomicAxesConstants
    limits: GbmProteomicAxesLimits
    signatures: tuple[GbmSignatureProfile, ...] = Field(
        min_length=MAX_SIGNATURES, max_length=MAX_SIGNATURES
    )
    source: GbmModelSource
    demo_request_digest: Sha256Digest
    profile_digest: Sha256Digest
    safety_class: Literal["research_use_only"] = "research_use_only"
    interpretation: Literal["non_prescriptive"] = "non_prescriptive"


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "MAX_BOOTSTRAPS",
    "MAX_JSON_SAFE_INTEGER",
    "MAX_MEASUREMENTS",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "MAX_SIGNATURES",
    "MAX_TOP_DRIVERS",
    "MIN_OBSERVED_MODEL_FEATURES",
    "PROFILE_ID",
    "SUPPORTED_COVERAGE_FRACTION",
    "SUPPORTED_SIGNATURE_IDS",
    "GbmEvidenceSummary",
    "GbmFeatureDriver",
    "GbmModelSource",
    "GbmNormalizationSummary",
    "GbmProteinEvidenceState",
    "GbmProteinMeasurement",
    "GbmProteomicAxesConstants",
    "GbmProteomicAxesLimits",
    "GbmProteomicAxesProfile",
    "GbmProteomicAxesProvenance",
    "GbmProteomicAxesRequest",
    "GbmProteomicAxesResult",
    "GbmReplayVerificationRequest",
    "GbmReplayVerificationResult",
    "GbmSignatureEstimate",
    "GbmSignatureProfile",
    "GbmSignatureSupport",
    "UnverifiedGbmProteomicAxesResult",
]
