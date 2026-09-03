"""Strict contracts for CPTAC GBM transcript--protein discordance evidence.

The runtime is a query over a locally fitted cohort artifact.  It deliberately
has no patient-measurement fields and cannot be used as a patient scorer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, FiniteFloat, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from glio_proteogen.research.cptac_gbm_cis_dosage.contracts import (
    ExactSourceLock,
    GeneSymbol,
)

from .canonical import profile_digest, request_digest, result_digest

ALGORITHM_ID = "cptac-gbm-transcript-protein-discordance"
ALGORITHM_VERSION = "1.0.0"
PROFILE_ID = "cptac-gbm-transcript-protein-discordance/1.0.0"
ARTIFACT_SCHEMA = "cptac-gbm-transcript-protein-discordance-artifact/1.0.0"
MAX_QUERY_GENES = 256
MAX_ARTIFACT_BYTES = 32 * 1_024 * 1_024
MAX_REQUEST_BYTES = 64 * 1_024
MAX_RESULT_BYTES = 4 * 1_024 * 1_024
MAX_REPLAY_BYTES = 8 * 1_024 * 1_024
_QUANTIZATION_DECIMALS = 8


def _quantized(value: float) -> float:
    rounded = round(float(value), _QUANTIZATION_DECIMALS)
    return 0.0 if rounded == 0.0 else rounded


class EvidenceSupport(StrEnum):
    LIMITED = "limited"
    ABSTAINED = "abstained"


class DerivationStatus(StrEnum):
    SYNTHETIC_UNVERIFIED = "synthetic_unverified"
    LOCALLY_VERIFIED_EXACT_SOURCES = "locally_verified_exact_sources"


class DiscordancePattern(StrEnum):
    POSITIVE_CONDITIONAL_RNA_ASSOCIATION = "positive_conditional_rna_association"
    INVERSE_CONDITIONAL_RNA_ASSOCIATION = "inverse_conditional_rna_association"
    PREDICTIVE_DIRECTION_INDETERMINATE = "predictive_direction_indeterminate"
    NO_INCREMENTAL_RNA_SUPPORT = "no_incremental_rna_support"
    INDETERMINATE = "indeterminate"


class TranscriptProteinDiscordanceRequest(FrozenModel):
    profile_id: Literal["cptac-gbm-transcript-protein-discordance/1.0.0"] = (
        "cptac-gbm-transcript-protein-discordance/1.0.0"
    )
    query_id: Identifier
    artifact_content_digest: Sha256Digest
    gene_symbols: tuple[GeneSymbol, ...] = Field(min_length=1, max_length=MAX_QUERY_GENES)

    @field_validator("gene_symbols")
    @classmethod
    def genes_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        del cls
        if len(value) != len(set(value)):
            raise ValueError("gene symbols must be unique")
        return value

    @property
    def request_digest(self) -> Sha256Digest:
        return request_digest(self)


class FiniteSampleInterval(FrozenModel):
    point_estimate: FiniteFloat
    lower: FiniteFloat
    upper: FiniteFloat
    coverage: FiniteFloat = Field(default=0.9, ge=0.9, le=0.9)
    replicates: int = Field(ge=1, le=256)
    method: Literal["deterministic_patient_bootstrap_nearest_rank"] = (
        "deterministic_patient_bootstrap_nearest_rank"
    )

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("interval lower bound exceeds upper bound")
        return self


class HeldOutModelMetrics(FrozenModel):
    n_oof: int = Field(ge=60, le=256)
    spearman: FiniteFloat | None = Field(default=None, ge=-1.0, le=1.0)
    r2_vs_fold_train_median: FiniteFloat
    mae: FiniteFloat = Field(ge=0.0)
    residual_mad: FiniteFloat = Field(ge=0.0)


class FoldConditionalEvidence(FrozenModel):
    valid_folds: int = Field(ge=4, le=5)
    converged_folds: int = Field(ge=0, le=5)
    conditional_rna_slope_median: FiniteFloat
    conditional_rna_slope_mad: FiniteFloat = Field(ge=0.0)
    conditional_rna_sign_stability: FiniteFloat | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    @model_validator(mode="after")
    def every_valid_fold_converged(self) -> Self:
        if self.converged_folds != self.valid_folds:
            raise ValueError("every valid fold must contain three converged models")
        return self


class BootstrapEvidence(FrozenModel):
    requested_replicates: int = Field(ge=16, le=256)
    successful_replicates: int = Field(ge=1, le=256)
    full_r2: FiniteSampleInterval
    delta_r2_vs_rna_only: FiniteSampleInterval
    delta_r2_vs_cnv_only: FiniteSampleInterval
    mae: FiniteSampleInterval
    residual_mad: FiniteSampleInterval
    conditional_rna_slope: FiniteSampleInterval
    seed: int = Field(ge=0, le=2**64 - 1)

    @model_validator(mode="after")
    def bootstrap_counts_and_intervals_reconcile(self) -> Self:
        minimum = (4 * self.requested_replicates + 4) // 5
        if not minimum <= self.successful_replicates <= self.requested_replicates:
            raise ValueError("bootstrap successful-replicate count is below the 80% gate")
        intervals = (
            self.full_r2,
            self.delta_r2_vs_rna_only,
            self.delta_r2_vs_cnv_only,
            self.mae,
            self.residual_mad,
            self.conditional_rna_slope,
        )
        if any(item.replicates != self.successful_replicates for item in intervals):
            raise ValueError("bootstrap intervals must use every successful replicate")
        return self


class GeneDiscordanceStatistics(FrozenModel):
    full_model: HeldOutModelMetrics
    rna_only_r2: FiniteFloat
    cnv_only_r2: FiniteFloat
    delta_r2_vs_rna_only: FiniteFloat
    delta_r2_vs_cnv_only: FiniteFloat
    folds: FoldConditionalEvidence
    bootstrap: BootstrapEvidence

    @model_validator(mode="after")
    def aggregate_and_bootstrap_points_reconcile(self) -> Self:
        expected_delta_rna = _quantized(
            float(self.full_model.r2_vs_fold_train_median) - float(self.rna_only_r2)
        )
        expected_delta_cnv = _quantized(
            float(self.full_model.r2_vs_fold_train_median) - float(self.cnv_only_r2)
        )
        if self.delta_r2_vs_rna_only != expected_delta_rna:
            raise ValueError("RNA-only delta R2 does not match the stored model metrics")
        if self.delta_r2_vs_cnv_only != expected_delta_cnv:
            raise ValueError("CNV-only delta R2 does not match the stored model metrics")
        point_pairs = (
            (self.bootstrap.full_r2.point_estimate, self.full_model.r2_vs_fold_train_median),
            (self.bootstrap.delta_r2_vs_rna_only.point_estimate, self.delta_r2_vs_rna_only),
            (self.bootstrap.delta_r2_vs_cnv_only.point_estimate, self.delta_r2_vs_cnv_only),
            (self.bootstrap.mae.point_estimate, self.full_model.mae),
            (self.bootstrap.residual_mad.point_estimate, self.full_model.residual_mad),
            (
                self.bootstrap.conditional_rna_slope.point_estimate,
                self.folds.conditional_rna_slope_median,
            ),
        )
        if any(observed != expected for observed, expected in point_pairs):
            raise ValueError("bootstrap point estimates do not match aggregate statistics")
        return self


class GeneTranscriptProteinEvidence(FrozenModel):
    gene_symbol: GeneSymbol
    support: EvidenceSupport
    pattern: DiscordancePattern | None = None
    statistics: GeneDiscordanceStatistics | None = None
    reasons: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    claim_ceiling: Literal["observational_cohort_pattern_not_patient_or_causal"] = (
        "observational_cohort_pattern_not_patient_or_causal"
    )

    @model_validator(mode="after")
    def evidence_matches_support(self) -> Self:
        if self.support is EvidenceSupport.ABSTAINED:
            if self.pattern is not None or self.statistics is not None:
                raise ValueError("abstained genes cannot carry fitted statistics")
        elif self.pattern is None or self.statistics is None:
            raise ValueError("limited genes require a pattern and fitted statistics")
        return self


class CohortArtifactSummary(FrozenModel):
    exact_common_measurement_count: int = Field(ge=60, le=256)
    patient_group_count: int = Field(ge=60, le=256)
    outer_fold_count: Literal[5] = 5
    common_gene_count: int = Field(gt=0, le=50_000)
    fitted_gene_count: int = Field(gt=0, le=50_000)
    contains_patient_measurements: Literal[False] = False
    contains_sample_headers: Literal[False] = False
    contains_patient_identifiers_or_hashes: Literal[False] = False
    contains_fold_membership: Literal[False] = False
    contains_oof_predictions_or_residuals: Literal[False] = False

    @model_validator(mode="after")
    def fitted_count_is_bounded_by_universe(self) -> Self:
        if self.fitted_gene_count > self.common_gene_count:
            raise ValueError("fitted gene count exceeds the common-gene universe")
        return self


class DiscordanceProvenance(FrozenModel):
    artifact_content_digest: Sha256Digest
    artifact_byte_digest: Sha256Digest
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    source_locks: tuple[ExactSourceLock, ...] = Field(min_length=2, max_length=2)
    cohort: CohortArtifactSummary
    derivation_status: DerivationStatus
    numpy_version: Literal["2.5.2"] = "2.5.2"
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"
    runtime_behavior: Literal["cohort_gene_query_never_patient_scoring"] = (
        "cohort_gene_query_never_patient_scoring"
    )


class _ResultBase(FrozenModel):
    algorithm_id: Literal["cptac-gbm-transcript-protein-discordance"] = (
        "cptac-gbm-transcript-protein-discordance"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["cptac-gbm-transcript-protein-discordance/1.0.0"] = (
        "cptac-gbm-transcript-protein-discordance/1.0.0"
    )
    query_id: Identifier
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    artifact_content_digest: Sha256Digest
    genes: tuple[GeneTranscriptProteinEvidence, ...] = Field(
        min_length=1,
        max_length=MAX_QUERY_GENES,
    )
    provenance: DiscordanceProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=4, max_length=12)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    patient_level_inference: Literal[False] = False
    maximum_support: Literal["limited"] = "limited"


class UnverifiedTranscriptProteinDiscordanceResult(_ResultBase):
    """Structurally valid replay input whose digest is not trusted."""


class TranscriptProteinDiscordanceResult(_ResultBase):
    @model_validator(mode="after")
    def receipt_is_content_bound(self) -> Self:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("profile digest does not match provenance")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("request digest does not match provenance")
        if self.artifact_content_digest != self.provenance.artifact_content_digest:
            raise ValueError("artifact digest does not match provenance")
        symbols = tuple(item.gene_symbol for item in self.genes)
        if symbols != tuple(sorted(symbols)) or len(symbols) != len(set(symbols)):
            raise ValueError("result genes must be unique and sorted")
        if self.result_digest != result_digest(self):
            raise ValueError("result digest does not match canonical content")
        return self


class ReplayVerificationRequest(FrozenModel):
    request: TranscriptProteinDiscordanceRequest
    result: UnverifiedTranscriptProteinDiscordanceResult


class ReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    artifact_digest_match: bool
    provided_result_digest_valid: bool
    recomputed_result_digest_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    provided_result_digest: Sha256Digest
    message: NonEmptyStr


class AlgorithmConstants(FrozenModel):
    outer_folds: Literal[5] = 5
    huber_k: FiniteFloat = Field(default=1.345, ge=1.345, le=1.345)
    maximum_irls_iterations: Literal[30] = 30
    irls_tolerance: FiniteFloat = Field(default=1e-8, ge=1e-8, le=1e-8)
    slope_ridge: FiniteFloat = Field(default=1e-8, ge=1e-8, le=1e-8)
    minimum_train_complete_cases: Literal[48] = 48
    minimum_test_complete_cases: Literal[3] = 3
    minimum_valid_folds: Literal[4] = 4
    minimum_oof_observations: Literal[60] = 60
    minimum_successful_bootstrap_replicates: Literal[103] = 103
    minimum_bootstrap_success_fraction: FiniteFloat = Field(default=0.8, ge=0.8, le=0.8)
    bootstrap_replicates: Literal[128] = 128
    bootstrap_coverage: FiniteFloat = Field(default=0.9, ge=0.9, le=0.9)
    fold_sign_stability_floor: FiniteFloat = Field(default=0.8, ge=0.8, le=0.8)
    quantization_decimals: Literal[8] = 8


class AlgorithmLimits(FrozenModel):
    max_query_genes: Literal[256] = 256
    max_artifact_bytes: Literal[33554432] = 33_554_432
    max_request_bytes: Literal[65536] = 65_536
    max_result_bytes: Literal[4194304] = 4_194_304
    max_replay_bytes: Literal[8388608] = 8_388_608


class TranscriptProteinDiscordanceProfile(FrozenModel):
    algorithm_id: Literal["cptac-gbm-transcript-protein-discordance"] = (
        "cptac-gbm-transcript-protein-discordance"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["cptac-gbm-transcript-protein-discordance/1.0.0"] = (
        "cptac-gbm-transcript-protein-discordance/1.0.0"
    )
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    numpy_version: Literal["2.5.2"] = "2.5.2"
    constants: AlgorithmConstants
    limits: AlgorithmLimits
    exact_source_locks: tuple[ExactSourceLock, ...] = Field(min_length=2, max_length=2)
    artifact_schema: Literal["cptac-gbm-transcript-protein-discordance-artifact/1.0.0"] = (
        "cptac-gbm-transcript-protein-discordance-artifact/1.0.0"
    )
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"
    public_http_mounted: Literal[False] = False
    public_cli_mounted: Literal[True] = True
    local_artifact_query_available: Literal[True] = True
    runtime_behavior: Literal["cohort_gene_query_never_patient_scoring"] = (
        "cohort_gene_query_never_patient_scoring"
    )
    claim_ceiling: Literal["limited_observational_cohort_pattern"] = (
        "limited_observational_cohort_pattern"
    )
    patient_measurement_input_permitted: Literal[False] = False
    local_trust_boundary: Literal["same_user_local_artifact_integrity_only"] = (
        "same_user_local_artifact_integrity_only"
    )
    cross_user_authenticity: Literal["signed_manifest_required_not_provided"] = (
        "signed_manifest_required_not_provided"
    )

    @model_validator(mode="after")
    def digest_is_valid(self) -> Self:
        if self.profile_digest != profile_digest(self):
            raise ValueError("profile digest does not match canonical profile content")
        return self


class FitReceipt(FrozenModel):
    artifact_content_digest: Sha256Digest
    artifact_byte_digest: Sha256Digest
    artifact_bytes: int = Field(gt=0, le=MAX_ARTIFACT_BYTES)
    fitted_gene_count: int = Field(gt=0, le=10_430)
    common_gene_count: Literal[10430] = 10_430
    exact_common_measurement_count: Literal[96] = 96
    derivation_status: Literal["locally_verified_exact_sources"] = "locally_verified_exact_sources"
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"
    safe_to_redistribute: Literal[False] = False


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "ARTIFACT_SCHEMA",
    "MAX_ARTIFACT_BYTES",
    "MAX_QUERY_GENES",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "PROFILE_ID",
    "AlgorithmConstants",
    "AlgorithmLimits",
    "BootstrapEvidence",
    "CohortArtifactSummary",
    "DerivationStatus",
    "DiscordancePattern",
    "DiscordanceProvenance",
    "EvidenceSupport",
    "ExactSourceLock",
    "FiniteSampleInterval",
    "FitReceipt",
    "FoldConditionalEvidence",
    "GeneDiscordanceStatistics",
    "GeneSymbol",
    "GeneTranscriptProteinEvidence",
    "HeldOutModelMetrics",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "TranscriptProteinDiscordanceProfile",
    "TranscriptProteinDiscordanceRequest",
    "TranscriptProteinDiscordanceResult",
    "UnverifiedTranscriptProteinDiscordanceResult",
]
