"""Strict contracts for fitted CPTAC GBM cohort cis-dosage evidence.

This lane reports cross-validated cohort associations for exact HGNC genes.  It
does not accept patient measurements and cannot emit a patient-level score.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .canonical import profile_digest, request_digest, result_digest

ALGORITHM_ID = "cptac-gbm-cis-dosage"
ALGORITHM_VERSION = "1.0.0"
PROFILE_ID = "cptac-gbm-cis-dosage/1.0.0"
ARTIFACT_SCHEMA = "cptac-gbm-cis-dosage-artifact/1.0.0"
MAX_QUERY_GENES = 256
MAX_ARTIFACT_BYTES = 8 * 1_024 * 1_024
MAX_REQUEST_BYTES = 64 * 1_024
MAX_RESULT_BYTES = 2 * 1_024 * 1_024
MAX_REPLAY_BYTES = 4 * 1_024 * 1_024

GeneSymbol = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Z][A-Z0-9.-]*$"),
]


class EvidenceSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class DerivationStatus(StrEnum):
    SYNTHETIC_UNVERIFIED = "synthetic_unverified"
    LOCALLY_VERIFIED_EXACT_SOURCES = "locally_verified_exact_sources"


class MechanismCategory(StrEnum):
    PROPAGATED = "propagated"
    BUFFERED = "buffered"
    DISCORDANT = "discordant"
    STABLE_OTHER = "stable_other"
    UNSTABLE_OR_MIXED = "unstable_or_mixed"


class SourcePositiveFlag(StrEnum):
    REPORTED_POSITIVE = "reported_positive"
    NOT_REPORTED_POSITIVE = "not_reported_positive"
    NOT_AVAILABLE = "not_available"


class ExactSourceLock(FrozenModel):
    source_id: Identifier
    sha256: Sha256Digest
    bytes: int = Field(gt=0, le=256 * 1_024 * 1_024)
    required_for_fit: bool
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"


class CisDosageEvidenceRequest(FrozenModel):
    profile_id: Literal["cptac-gbm-cis-dosage/1.0.0"] = "cptac-gbm-cis-dosage/1.0.0"
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
    def request_digest(self) -> str:
        return request_digest(self)


class OutOfFoldMetrics(FrozenModel):
    n_oof: int = Field(ge=60, le=256)
    pearson: float | None = Field(default=None, ge=-1.0, le=1.0)
    spearman: float | None = Field(default=None, ge=-1.0, le=1.0)
    r2_vs_fold_train_median: float | None = None
    direction_accuracy_vs_fold_train_median: float | None = Field(default=None, ge=0.0, le=1.0)


class ProteinOutOfFoldMetrics(OutOfFoldMetrics):
    delta_r2_vs_rna_only: float | None = None
    delta_r2_vs_cnv_only: float | None = None


class FoldCoefficientEvidence(FrozenModel):
    valid_rna_folds: int = Field(ge=4, le=5)
    valid_protein_folds: int = Field(ge=4, le=5)
    converged_rna_folds: int = Field(ge=0, le=5)
    converged_protein_folds: int = Field(ge=0, le=5)
    a_cnv_to_rna_median: float
    b_rna_to_protein_given_cnv_median: float
    cprime_cnv_to_protein_given_rna_median: float
    indirect_a_times_b_median: float
    total_proxy_median: float
    a_sign_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    b_sign_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    cprime_sign_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    indirect_sign_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    total_sign_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    a_fold_mad: float = Field(ge=0.0)
    b_fold_mad: float = Field(ge=0.0)
    cprime_fold_mad: float = Field(ge=0.0)


class TableS3SourceFlags(FrozenModel):
    cnv_rna: SourcePositiveFlag
    cnv_protein: SourcePositiveFlag
    interpretation: Literal["absence_is_not_a_negative_or_tested_null"] = (
        "absence_is_not_a_negative_or_tested_null"
    )


class GeneCisDosageEvidence(FrozenModel):
    gene_symbol: GeneSymbol
    support: EvidenceSupport
    rna: OutOfFoldMetrics | None = None
    protein: ProteinOutOfFoldMetrics | None = None
    coefficients: FoldCoefficientEvidence | None = None
    mechanism: MechanismCategory | None = None
    rna_evidence_gate: bool | None = None
    protein_evidence_gate: bool | None = None
    table_s3_source_flags: TableS3SourceFlags
    reasons: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    claim_ceiling: Literal["observational_cohort_association_not_causal"] = (
        "observational_cohort_association_not_causal"
    )

    @model_validator(mode="after")
    def evidence_matches_support(self) -> Self:
        fitted = (self.rna, self.protein, self.coefficients, self.mechanism)
        gates = (self.rna_evidence_gate, self.protein_evidence_gate)
        if self.support is EvidenceSupport.ABSTAINED:
            if any(value is not None for value in (*fitted, *gates)):
                raise ValueError("abstained genes cannot carry fitted evidence")
            return self
        if any(value is None for value in (*fitted, *gates)):
            raise ValueError("estimated genes require complete fitted evidence")
        coefficients = self.coefficients
        if coefficients is None:
            raise ValueError("estimated evidence requires coefficients")
        if self.support is EvidenceSupport.SUPPORTED:
            if self.rna_evidence_gate is not True or self.protein_evidence_gate is not True:
                raise ValueError("supported evidence must pass both OOF gates")
            if coefficients.converged_rna_folds < 4 or coefficients.converged_protein_folds < 4:
                raise ValueError("supported evidence requires converged folds")
            if (coefficients.indirect_sign_consistency or 0.0) < 0.8:
                raise ValueError("supported evidence requires stable indirect direction")
            if (coefficients.total_sign_consistency or 0.0) < 0.8:
                raise ValueError("supported evidence requires stable total direction")
        return self


class CohortArtifactSummary(FrozenModel):
    exact_common_measurement_count: int = Field(ge=60, le=256)
    patient_group_count: int = Field(ge=60, le=256)
    outer_fold_count: Literal[5] = 5
    common_gene_count: int = Field(gt=0, le=50_000)
    fitted_gene_count: int = Field(gt=0, le=50_000)
    table_s3_flags_included: bool
    contains_patient_measurements: Literal[False] = False
    contains_sample_headers: Literal[False] = False
    contains_patient_identifiers_or_hashes: Literal[False] = False
    contains_fold_membership: Literal[False] = False


class CisDosageProvenance(FrozenModel):
    artifact_content_digest: Sha256Digest
    artifact_byte_digest: Sha256Digest
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    source_locks: tuple[ExactSourceLock, ...] = Field(min_length=2, max_length=3)
    cohort: CohortArtifactSummary
    derivation_status: DerivationStatus
    numpy_version: NonEmptyStr
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"
    runtime_behavior: Literal["cohort_fitted_gene_query_never_patient_scoring"] = (
        "cohort_fitted_gene_query_never_patient_scoring"
    )


class CisDosageEvidenceResult(FrozenModel):
    algorithm_id: Literal["cptac-gbm-cis-dosage"] = "cptac-gbm-cis-dosage"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["cptac-gbm-cis-dosage/1.0.0"] = "cptac-gbm-cis-dosage/1.0.0"
    query_id: Identifier
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    artifact_content_digest: Sha256Digest
    genes: tuple[GeneCisDosageEvidence, ...] = Field(min_length=1, max_length=MAX_QUERY_GENES)
    provenance: CisDosageProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=3, max_length=12)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    patient_level_inference: Literal[False] = False

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


class UnverifiedCisDosageEvidenceResult(FrozenModel):
    algorithm_id: Literal["cptac-gbm-cis-dosage"] = "cptac-gbm-cis-dosage"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["cptac-gbm-cis-dosage/1.0.0"] = "cptac-gbm-cis-dosage/1.0.0"
    query_id: Identifier
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    artifact_content_digest: Sha256Digest
    genes: tuple[GeneCisDosageEvidence, ...] = Field(min_length=1, max_length=MAX_QUERY_GENES)
    provenance: CisDosageProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=3, max_length=12)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    patient_level_inference: Literal[False] = False


class ReplayVerificationRequest(FrozenModel):
    request: CisDosageEvidenceRequest
    result: UnverifiedCisDosageEvidenceResult


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


class SourceVerification(FrozenModel):
    source_id: Identifier
    expected_digest: Sha256Digest
    observed_digest: Sha256Digest
    expected_bytes: int = Field(gt=0)
    observed_bytes: int = Field(ge=0)
    verified: bool


class SourceVerificationResult(FrozenModel):
    verified: bool
    sources: tuple[SourceVerification, ...] = Field(min_length=2, max_length=3)
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"


class FitReceipt(FrozenModel):
    artifact_content_digest: Sha256Digest
    artifact_byte_digest: Sha256Digest
    artifact_bytes: int = Field(gt=0, le=MAX_ARTIFACT_BYTES)
    fitted_gene_count: int = Field(gt=0, le=50_000)
    common_gene_count: int = Field(gt=0, le=50_000)
    exact_common_measurement_count: int = Field(ge=60, le=256)
    table_s3_flags_included: bool
    derivation_status: Literal["locally_verified_exact_sources"] = "locally_verified_exact_sources"
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"
    safe_to_redistribute: Literal[False] = False


class AlgorithmConstants(FrozenModel):
    outer_folds: Literal[5] = 5
    seed: Literal[20260829] = 20_260_829
    huber_k: float = Field(default=1.345, gt=0.0)
    maximum_irls_iterations: Literal[30] = 30
    irls_tolerance: float = Field(default=1e-8, gt=0.0)
    slope_ridge: float = Field(default=1e-8, gt=0.0)
    minimum_train_complete_cases: Literal[48] = 48
    minimum_test_complete_cases: Literal[3] = 3
    minimum_valid_folds: Literal[4] = 4
    minimum_oof_observations: Literal[60] = 60
    stability_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    quantization_decimals: Literal[8] = 8
    production_exact_common_measurements: Literal[96] = 96
    production_patient_groups: Literal[96] = 96
    production_common_genes: Literal[10430] = 10_430
    production_fitted_genes: Literal[9457] = 9_457
    s3_zero_semantics: Literal["not_reported_positive_never_negative"] = (
        "not_reported_positive_never_negative"
    )


class AlgorithmLimits(FrozenModel):
    max_query_genes: Literal[256] = 256
    max_artifact_bytes: Literal[8388608] = 8_388_608
    max_request_bytes: Literal[65536] = 65_536
    max_result_bytes: Literal[2097152] = 2_097_152
    max_replay_bytes: Literal[4194304] = 4_194_304


class CisDosageProfile(FrozenModel):
    algorithm_id: Literal["cptac-gbm-cis-dosage"] = "cptac-gbm-cis-dosage"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["cptac-gbm-cis-dosage/1.0.0"] = "cptac-gbm-cis-dosage/1.0.0"
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    numpy_version: Literal["2.5.2"] = "2.5.2"
    constants: AlgorithmConstants
    limits: AlgorithmLimits
    exact_source_locks: tuple[ExactSourceLock, ...] = Field(min_length=3, max_length=3)
    artifact_schema: Literal["cptac-gbm-cis-dosage-artifact/1.0.0"] = (
        "cptac-gbm-cis-dosage-artifact/1.0.0"
    )
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"
    public_http_mounted: Literal[False] = False
    runtime_behavior: Literal["cohort_fitted_gene_query_never_patient_scoring"] = (
        "cohort_fitted_gene_query_never_patient_scoring"
    )
    claim_ceiling: Literal["observational_cohort_association_not_causal"] = (
        "observational_cohort_association_not_causal"
    )
    table_s3_semantics: Literal["positive_flag_or_not_reported_positive_never_negative"] = (
        "positive_flag_or_not_reported_positive_never_negative"
    )
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


def finite_or_none(value: float | None) -> float | None:
    """Narrow helper used by artifact decoding."""

    if value is not None and not math.isfinite(value):
        raise ValueError("non-finite evidence is forbidden")
    return value


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
    "CisDosageEvidenceRequest",
    "CisDosageEvidenceResult",
    "CisDosageProfile",
    "CisDosageProvenance",
    "CohortArtifactSummary",
    "DerivationStatus",
    "EvidenceSupport",
    "ExactSourceLock",
    "FitReceipt",
    "FoldCoefficientEvidence",
    "GeneCisDosageEvidence",
    "GeneSymbol",
    "MechanismCategory",
    "OutOfFoldMetrics",
    "ProteinOutOfFoldMetrics",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "SourcePositiveFlag",
    "SourceVerification",
    "SourceVerificationResult",
    "TableS3SourceFlags",
    "UnverifiedCisDosageEvidenceResult",
    "finite_or_none",
]
