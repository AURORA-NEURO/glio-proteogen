"""Research-only contracts for bulk-protein Neftel program evidence.

The results are program-level evidence in a bulk specimen. They are not cell fractions,
diagnoses, molecular subtypes, or claims that a measured protein came from a tumor cell.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, StringConstraints, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .canonical import canonical_request_digest, result_payload_digest
from .catalog import is_protein_background_symbol, normalize_symbol

ALGORITHM_ID = "neftel-bulk-protein-programs"
ALGORITHM_VERSION = "1.0.0"
PROFILE_ID = "neftel-bulk-protein-programs/1.0.0"
MAX_OBSERVATIONS = 4_096
MAX_BOOTSTRAPS = 256
MAX_PERMUTATIONS = 2_048
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 1 * 1_024 * 1_024
MAX_REPLAY_BYTES = 4 * 1_024 * 1_024

GeneSymbol = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"),
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


class ProgramClassification(StrEnum):
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


class ProgramKind(StrEnum):
    SOURCE_META_MODULE = "source_meta_module"
    DERIVED_PROGRAM_FAMILY = "derived_program_family"


class ExactProgramId(StrEnum):
    MES2 = "MES2"
    MES1 = "MES1"
    AC = "AC"
    OPC = "OPC"
    NPC1 = "NPC1"
    NPC2 = "NPC2"
    G1S = "G1/S"
    G2M = "G2/M"


class ProgramFamilyId(StrEnum):
    ASTROCYTE_LIKE = "astrocyte_like"
    OLIGODENDROCYTE_PROGENITOR_LIKE = "oligodendrocyte_progenitor_like"
    NEURAL_PROGENITOR_LIKE = "neural_progenitor_like"
    MESENCHYMAL_LIKE = "mesenchymal_like"
    CELL_CYCLE = "cell_cycle"


class ProteinProgramObservation(FrozenModel):
    observation_id: Identifier
    gene_symbol: GeneSymbol
    state: ProteinEvidenceState
    standardized_effect: float | None = Field(default=None, ge=-20.0, le=20.0)
    standard_error: float | None = Field(default=None, gt=0.0, le=20.0)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_digest: Sha256Digest

    @model_validator(mode="after")
    def numerical_values_match_state(self) -> Self:
        active = self.state in {
            ProteinEvidenceState.OBSERVED,
            ProteinEvidenceState.LEFT_CENSORED,
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


class ProteinProgramRequest(FrozenModel):
    profile_id: Literal["neftel-bulk-protein-programs/1.0.0"] = (
        "neftel-bulk-protein-programs/1.0.0"
    )
    sample_id: Identifier
    observations: tuple[ProteinProgramObservation, ...] = Field(
        min_length=1,
        max_length=MAX_OBSERVATIONS,
    )
    bootstrap_replicates: int = Field(default=64, ge=16, le=MAX_BOOTSTRAPS)
    permutation_replicates: int = Field(default=256, ge=64, le=MAX_PERMUTATIONS)
    background_mode: Literal["request_observed_proteome"] = "request_observed_proteome"
    effect_scale: Literal["standardized_log2_abundance_contrast"]
    effect_reference_id: Identifier

    @field_validator("observations")
    @classmethod
    def observations_are_unique(
        cls,
        values: tuple[ProteinProgramObservation, ...],
    ) -> tuple[ProteinProgramObservation, ...]:
        identifiers = tuple(item.observation_id for item in values)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{cls.__name__} observation identifiers must be unique")
        normalized = tuple(normalize_symbol(item.gene_symbol) for item in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError(
                f"{cls.__name__} gene symbols must be unique after profile-pinned alias normalization"
            )
        invalid_active_symbols = sorted(
            {
                normalize_symbol(item.gene_symbol)
                for item in values
                if item.state
                in {ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED}
                and not is_protein_background_symbol(item.gene_symbol)
            }
        )
        if invalid_active_symbols:
            preview = ", ".join(invalid_active_symbols[:5])
            raise ValueError(
                "active evidence must resolve to the profile-pinned HGNC-UniProt protein "
                f"background; rejected: {preview}"
            )
        return values

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class MethodEstimate(FrozenModel):
    support: AnalysisSupport
    score: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    effective_sample_size: float = Field(ge=0.0)
    bootstrap_replicates_used: int = Field(ge=0, le=MAX_BOOTSTRAPS)
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def interval_matches_support(self) -> Self:
        numeric = (self.score, self.lower_bound, self.upper_bound)
        if self.support is AnalysisSupport.ABSTAINED:
            if any(value is not None for value in numeric) or self.reason is None:
                raise ValueError("abstained methods require a reason and no estimate")
        else:
            if any(value is None for value in numeric):
                raise ValueError("estimated methods require a complete interval")
            if self.support is AnalysisSupport.SUPPORTED and self.reason is not None:
                raise ValueError("supported methods cannot carry a limitation reason")
            if self.support is AnalysisSupport.LIMITED and self.reason is None:
                raise ValueError("limited methods require a limitation reason")
            score = cast("float", self.score)
            lower = cast("float", self.lower_bound)
            upper = cast("float", self.upper_bound)
            if not lower <= score <= upper:
                raise ValueError("method interval must contain its score")
        return self


class RankEnrichmentEstimate(MethodEstimate):
    permutation_replicates_used: int = Field(ge=0, le=MAX_PERMUTATIONS)
    null_standard_deviation: float | None = Field(default=None, ge=0.0)
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    q_value: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def null_statistics_match_support(self) -> Self:
        statistics = (self.null_standard_deviation, self.p_value, self.q_value)
        if self.support is AnalysisSupport.ABSTAINED:
            if any(value is not None for value in statistics):
                raise ValueError("abstained rank estimates cannot carry null statistics")
            if self.permutation_replicates_used != 0:
                raise ValueError("abstained rank estimates use zero permutations")
        elif any(value is None for value in statistics) or self.permutation_replicates_used == 0:
            raise ValueError("estimated rank enrichment requires permutation null statistics")
        return self


class ProgramEvidenceCounts(FrozenModel):
    source_marker_count: int = Field(ge=1, le=100)
    eligible_protein_markers: int = Field(ge=1, le=100)
    catalog_non_protein_loci: int = Field(ge=0, le=10)
    observed_markers: int = Field(ge=0, le=100)
    left_censored_markers: int = Field(ge=0, le=100)
    explicitly_missing_markers: int = Field(ge=0, le=100)
    unsupported_markers: int = Field(ge=0, le=100)
    unreported_markers: int = Field(ge=0, le=100)
    active_coverage: float = Field(ge=0.0, le=1.0)
    observed_background_proteins: int = Field(ge=0, le=MAX_OBSERVATIONS)


class MarkerDriver(FrozenModel):
    normalized_symbol: GeneSymbol
    source_symbols: tuple[GeneSymbol, ...] = Field(min_length=1, max_length=8)
    source_ranks: tuple[int, ...] = Field(min_length=1, max_length=8)
    evidence_state: ProteinEvidenceState
    value_role: Literal["observed_point", "left_censored_upper_limit"]
    standardized_effect: float
    reliability_weight: float = Field(gt=0.0)
    location_influence: float | None = None
    rank_influence: float | None = None


class MarkerFamilyAblation(FrozenModel):
    omitted_family: NonEmptyStr
    markers_removed: int = Field(ge=1, le=100)
    location_delta: float | None = None
    rank_delta: float | None = None


class ProgramEvidence(FrozenModel):
    program_id: ExactProgramId | ProgramFamilyId
    program_kind: ProgramKind
    source_programs: tuple[ExactProgramId, ...] = Field(min_length=1, max_length=2)
    support: AnalysisSupport
    classification: ProgramClassification
    location: MethodEstimate
    rank_enrichment: RankEnrichmentEstimate
    method_agreement: MethodAgreement
    evidence_counts: ProgramEvidenceCounts
    top_drivers: tuple[MarkerDriver, ...] = Field(default=(), max_length=5)
    marker_family_ablations: tuple[MarkerFamilyAblation, ...] = Field(default=(), max_length=3)
    abstention_reasons: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def interpretation_matches_support(self) -> Self:
        if self.support is AnalysisSupport.ABSTAINED:
            if self.classification is not ProgramClassification.NOT_ESTIMABLE:
                raise ValueError("abstained programs must be not_estimable")
            if not self.abstention_reasons:
                raise ValueError("abstained programs require reasons")
        elif self.classification is ProgramClassification.NOT_ESTIMABLE:
            raise ValueError("estimated programs cannot be not_estimable")
        return self


class ProteinProgramProvenance(FrozenModel):
    engine: Literal["neftel-bulk-protein-programs/1.0.0"] = (
        "neftel-bulk-protein-programs/1.0.0"
    )
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    catalog_content_digest: Sha256Digest
    catalog_artifact_digest: Sha256Digest
    exact_source_program_digest: Sha256Digest
    table_s2_source_digest: Sha256Digest
    hgnc_source_digest: Sha256Digest
    numpy_version: NonEmptyStr
    computational_digest: Sha256Digest
    bootstrap_seed: int = Field(ge=0, le=2**53 - 1)
    rank_permutation_seed: int = Field(ge=0, le=2**53 - 1)
    observation_source_digests: tuple[Sha256Digest, ...] = Field(max_length=MAX_OBSERVATIONS)


class ProteinProgramResult(FrozenModel):
    algorithm_id: Literal["neftel-bulk-protein-programs"] = "neftel-bulk-protein-programs"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["neftel-bulk-protein-programs/1.0.0"] = (
        "neftel-bulk-protein-programs/1.0.0"
    )
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    program_evidence: tuple[ProgramEvidence, ...] = Field(min_length=13, max_length=13)
    provenance: ProteinProgramProvenance
    output_semantics: Literal["bulk_protein_program_evidence"] = (
        "bulk_protein_program_evidence"
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
        identifiers = tuple(item.program_id for item in self.program_evidence)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("program result identifiers must be unique")
        return self


class UnverifiedProteinProgramResult(FrozenModel):
    """Structurally valid caller receipt accepted before integrity verification."""

    algorithm_id: Literal["neftel-bulk-protein-programs"] = (
        "neftel-bulk-protein-programs"
    )
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["neftel-bulk-protein-programs/1.0.0"] = (
        "neftel-bulk-protein-programs/1.0.0"
    )
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    program_evidence: tuple[ProgramEvidence, ...] = Field(min_length=13, max_length=13)
    provenance: ProteinProgramProvenance
    output_semantics: Literal["bulk_protein_program_evidence"] = (
        "bulk_protein_program_evidence"
    )
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=12)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True


class ReplayVerificationRequest(FrozenModel):
    request: ProteinProgramRequest
    result: ProteinProgramResult | UnverifiedProteinProgramResult


class ReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr


class NeftelAlgorithmConstants(FrozenModel):
    location_estimator: Literal["one_sided_huber_location_bisection_v1"]
    rank_estimator: Literal["reliability_weighted_mean_percentile_rank_v1"]
    bootstrap_policy: Literal["request_digest_seeded_normal_limit_perturbation_v1"]
    family_pooling_policy: Literal["equal_source_program_equal_marker_mass_v1"]
    rank_null_policy: Literal["two_sided_global_percentile_permutation_bh_v1"]
    huber_delta: float = Field(gt=0.0)
    standard_error_floor: float = Field(gt=0.0)
    location_ridge: float = Field(gt=0.0)
    activation_threshold: float = Field(gt=0.0)
    rank_neutral_threshold: float = Field(gt=0.0, lt=1.0)
    rank_q_threshold: float = Field(gt=0.0, le=1.0)
    exploratory_minimum_active_markers: int = Field(gt=0)
    exploratory_minimum_observed_markers: int = Field(gt=0)
    exploratory_minimum_active_coverage: float = Field(gt=0.0, le=1.0)
    exploratory_minimum_effective_sample_size: float = Field(gt=0.0)
    supported_minimum_active_markers: int = Field(gt=0)
    supported_minimum_observed_markers: int = Field(gt=0)
    supported_minimum_active_coverage: float = Field(gt=0.0, le=1.0)
    supported_minimum_effective_sample_size: float = Field(gt=0.0)
    minimum_rank_background: int = Field(gt=0)
    interval_lower_quantile: float = Field(ge=0.0, lt=0.5)
    interval_upper_quantile: float = Field(gt=0.5, le=1.0)
    quantization_decimals: int = Field(ge=0, le=15)
    random_seed_bytes: int = Field(ge=4, le=32)
    default_permutation_replicates: int = Field(ge=64, le=MAX_PERMUTATIONS)


class NeftelAlgorithmProfile(FrozenModel):
    algorithm_id: Literal["neftel-bulk-protein-programs"] = "neftel-bulk-protein-programs"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["neftel-bulk-protein-programs/1.0.0"] = (
        "neftel-bulk-protein-programs/1.0.0"
    )
    constants: NeftelAlgorithmConstants
    numpy_version: NonEmptyStr
    catalog_content_digest: Sha256Digest
    catalog_artifact_digest: Sha256Digest
    exact_source_program_digest: Sha256Digest
    table_s2_source_digest: Sha256Digest
    hgnc_source_digest: Sha256Digest
    profile_digest: Sha256Digest
    safety_class: Literal["research_use_only"] = "research_use_only"
    interpretation: Literal["bulk_protein_program_evidence_non_prescriptive"] = (
        "bulk_protein_program_evidence_non_prescriptive"
    )


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "MAX_BOOTSTRAPS",
    "MAX_OBSERVATIONS",
    "MAX_PERMUTATIONS",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "PROFILE_ID",
    "AnalysisSupport",
    "ExactProgramId",
    "MarkerDriver",
    "MarkerFamilyAblation",
    "MethodAgreement",
    "MethodEstimate",
    "NeftelAlgorithmConstants",
    "NeftelAlgorithmProfile",
    "ProgramClassification",
    "ProgramEvidence",
    "ProgramEvidenceCounts",
    "ProgramFamilyId",
    "ProgramKind",
    "ProteinEvidenceState",
    "ProteinProgramObservation",
    "ProteinProgramProvenance",
    "ProteinProgramRequest",
    "ProteinProgramResult",
    "RankEnrichmentEstimate",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "UnverifiedProteinProgramResult",
]
