"""Strict contracts for the published GBMPurity NumPy inference lane.

The lane is intentionally RNA-only.  It estimates the malignant-cell fraction of
primary IDH-wildtype glioblastoma bulk RNA-seq samples on the exact source feature
space.  It does not infer immune composition, protein abundance, diagnosis,
prognosis, treatment response, or clinical action.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .canonical import canonical_request_digest, result_payload_digest, sha256_digest

ALGORITHM_ID = "gbm-rna-tumor-purity"
ALGORITHM_VERSION = "1.0.0"
PROFILE_ID = "gbm-rna-tumor-purity/1.0.0"
MODEL_ID = "gbmpurity-primary-idhwt-rna/1.0.0"
MODEL_FEATURE_COUNT = 5_829
MINIMUM_MODEL_GENE_COVERAGE = 0.80
SUPPORTED_MODEL_GENE_COVERAGE = 0.99
MAX_INPUT_GENES = 40_000
MAX_REQUEST_BYTES = 4 * 1_024 * 1_024
MAX_RESULT_BYTES = 2 * 1_024 * 1_024
MAX_REPLAY_BYTES = 8 * 1_024 * 1_024
TOP_ATTRIBUTION_LIMIT = 20

GeneSymbol = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    ),
]


class PuritySupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class ClippingState(StrEnum):
    NONE = "none"
    LOWER_BOUND = "lower_bound"
    UPPER_BOUND = "upper_bound"
    NOT_APPLICABLE = "not_applicable"


class AttributionDirection(StrEnum):
    RAISES_RAW_ESTIMATE = "raises_raw_estimate"
    LOWERS_RAW_ESTIMATE = "lowers_raw_estimate"
    ZERO_LOCAL_CONTRIBUTION = "zero_local_contribution"


class GbmRnaContextAttestation(FrozenModel):
    """Caller-owned scope and preprocessing declaration required by the source model."""

    schema_version: Literal["glio-proteogen.gbm-rna-context-attestation/1.0.0"]
    organism: Literal["Homo sapiens"]
    disease_context: Literal["primary_IDH_wildtype_glioblastoma"]
    specimen: Literal["bulk_tumor_tissue"]
    assay: Literal["bulk_RNA_sequencing"]
    value_semantics: Literal["raw_nonnegative_gene_counts"]
    batch_corrected: Literal[False]
    caller_authorizes_missing_gene_zero_fill: Literal[True]
    research_use_only: Literal[True]


REQUIRED_CONTEXT = GbmRnaContextAttestation(
    schema_version="glio-proteogen.gbm-rna-context-attestation/1.0.0",
    organism="Homo sapiens",
    disease_context="primary_IDH_wildtype_glioblastoma",
    specimen="bulk_tumor_tissue",
    assay="bulk_RNA_sequencing",
    value_semantics="raw_nonnegative_gene_counts",
    batch_corrected=False,
    caller_authorizes_missing_gene_zero_fill=True,
    research_use_only=True,
)


class RawGeneCount(FrozenModel):
    gene_symbol: GeneSymbol
    raw_count: float = Field(ge=0.0, le=1.0e15)


class GbmRnaPurityRequest(FrozenModel):
    schema_version: Literal["glio-proteogen.gbm-rna-purity-request/1.0.0"] = (
        "glio-proteogen.gbm-rna-purity-request/1.0.0"
    )
    sample_id: Identifier
    profile_id: Literal["gbm-rna-tumor-purity/1.0.0"] = "gbm-rna-tumor-purity/1.0.0"
    context: GbmRnaContextAttestation
    counts_provenance_digest: Sha256Digest
    counts: tuple[RawGeneCount, ...] = Field(min_length=1, max_length=MAX_INPUT_GENES)

    @field_validator("counts")
    @classmethod
    def genes_are_unique(cls, values: tuple[RawGeneCount, ...]) -> tuple[RawGeneCount, ...]:
        symbols = tuple(item.gene_symbol for item in values)
        if len(symbols) != len(set(symbols)):
            raise ValueError("gene symbols must be unique; duplicate counts are not summed")
        return values

    @model_validator(mode="after")
    def exact_context_is_required(self) -> Self:
        if self.context != REQUIRED_CONTEXT:
            raise ValueError("context attestation does not match the frozen GBMPurity scope")
        return self


class ModelCoverage(FrozenModel):
    model_feature_count: Literal[5_829] = 5_829
    supplied_gene_count: int = Field(ge=1, le=MAX_INPUT_GENES)
    recognized_model_gene_count: int = Field(ge=0, le=MODEL_FEATURE_COUNT)
    missing_model_gene_count: int = Field(ge=0, le=MODEL_FEATURE_COUNT)
    ignored_non_model_gene_count: int = Field(ge=0, le=MAX_INPUT_GENES)
    nonzero_model_gene_count: int = Field(ge=0, le=MODEL_FEATURE_COUNT)
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    recognized_raw_count_sum: float = Field(ge=0.0)
    missing_gene_policy: Literal["source_parity_zero_fill_after_80_percent_gate"] = (
        "source_parity_zero_fill_after_80_percent_gate"
    )

    @model_validator(mode="after")
    def counts_balance(self) -> Self:
        if self.recognized_model_gene_count + self.missing_model_gene_count != MODEL_FEATURE_COUNT:
            raise ValueError("recognized and missing model-gene counts do not balance")
        if (
            self.recognized_model_gene_count + self.ignored_non_model_gene_count
            != self.supplied_gene_count
        ):
            raise ValueError("recognized and ignored supplied-gene counts do not balance")
        expected = self.recognized_model_gene_count / MODEL_FEATURE_COUNT
        if abs(self.coverage_fraction - expected) > 1.0e-9:
            raise ValueError("coverage fraction does not match recognized model genes")
        return self


class HiddenActivationTrace(FrozenModel):
    first_layer_active_nodes: int = Field(ge=0, le=32)
    second_layer_active_nodes: int = Field(ge=0, le=16)
    first_layer_activations: tuple[float, ...] = Field(min_length=32, max_length=32)
    second_layer_activations: tuple[float, ...] = Field(min_length=16, max_length=16)
    activation_pattern_digest: Sha256Digest


class GeneLocalAttribution(FrozenModel):
    rank: int = Field(ge=1, le=TOP_ATTRIBUTION_LIMIT)
    gene_symbol: GeneSymbol
    transformed_expression: float = Field(ge=0.0)
    local_gradient: float
    raw_output_contribution: float
    direction: AttributionDirection


class LocalLinearExplanation(FrozenModel):
    method: Literal["exact_active_relu_path_decomposition"] = "exact_active_relu_path_decomposition"
    top_gene_attributions: tuple[GeneLocalAttribution, ...] = Field(
        max_length=TOP_ATTRIBUTION_LIMIT
    )
    all_gene_contribution_sum: float
    active_path_bias_contribution: float
    reconstructed_raw_output: float
    reconstruction_absolute_error: float = Field(ge=0.0)
    clipping_changes_local_interpretation: bool
    interpretation: Literal["local_piecewise_linear_attribution_not_causal_gene_importance"] = (
        "local_piecewise_linear_attribution_not_causal_gene_importance"
    )


class GbmRnaPurityEstimate(FrozenModel):
    malignant_cell_fraction: float = Field(ge=0.0, le=1.0)
    raw_unclipped_output: float
    clipping_state: ClippingState
    model_output_semantics: Literal["published_GBMPurity_estimated_malignant_cell_fraction"] = (
        "published_GBMPurity_estimated_malignant_cell_fraction"
    )


class GbmRnaPurityDiagnostics(FrozenModel):
    preprocessing: Literal["source_order_zero_fill_then_RPK_share_times_1e4_then_log2_plus_1"] = (
        "source_order_zero_fill_then_RPK_share_times_1e4_then_log2_plus_1"
    )
    network: Literal["5829_to_32_relu_to_16_relu_to_1_linear_eval_mode"] = (
        "5829_to_32_relu_to_16_relu_to_1_linear_eval_mode"
    )
    dropout_active: Literal[False] = False
    inference_dtype: Literal["float32"] = "float32"
    finite_inference: bool
    transformed_input_sum: float = Field(ge=0.0)
    transformed_input_maximum: float = Field(ge=0.0)
    hidden_trace: HiddenActivationTrace | None


class GbmRnaPurityProvenance(FrozenModel):
    source_repository: Literal["https://github.com/scmpht/GBMPurity"]
    source_commit: Literal["af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950"]
    source_model_sha256: Literal[
        "sha256:80abd8d8f4875799f839701bec655d2e4753c750e63e60b9119b8b66342025c7"
    ]
    source_gene_lengths_sha256: Literal[
        "sha256:de148837ab4d487b3fd86436f63e95b451fa4a305c5bf8d5eb094c117941884b"
    ]
    converted_artifact_digest: Sha256Digest
    converted_artifact_file_sha256: Sha256Digest
    feature_order_digest: Sha256Digest
    weight_tensor_digest: Sha256Digest
    source_license: Literal["MIT"]
    source_license_sha256: Literal[
        "sha256:3f0041f0cfe77a6f4153e1465b1590b744102d9e8948203bcb56d9b244367ef7"
    ]
    article_doi: Literal["10.1093/neuonc/noaf026"]
    article_license: Literal["CC-BY-4.0"]
    transformation_notice: NonEmptyStr


class _GbmRnaPurityResultDocument(FrozenModel):
    schema_version: Literal["glio-proteogen.gbm-rna-purity-result/1.0.0"] = (
        "glio-proteogen.gbm-rna-purity-result/1.0.0"
    )
    algorithm_id: Literal["gbm-rna-tumor-purity"] = "gbm-rna-tumor-purity"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["gbm-rna-tumor-purity/1.0.0"] = "gbm-rna-tumor-purity/1.0.0"
    model_id: Literal["gbmpurity-primary-idhwt-rna/1.0.0"] = "gbmpurity-primary-idhwt-rna/1.0.0"
    sample_id: Identifier
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    result_digest: Sha256Digest
    support: PuritySupport
    coverage: ModelCoverage
    estimate: GbmRnaPurityEstimate | None
    diagnostics: GbmRnaPurityDiagnostics
    explanation: LocalLinearExplanation | None
    uncertainty_status: Literal["not_available_in_published_single_model"] = (
        "not_available_in_published_single_model"
    )
    uncertainty_reason: NonEmptyStr
    provenance: GbmRnaPurityProvenance
    abstention_reasons: tuple[NonEmptyStr, ...]
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1)
    safety_class: Literal["research_use_only_non_prescriptive"] = (
        "research_use_only_non_prescriptive"
    )

    @model_validator(mode="after")
    def support_and_payload_agree(self) -> Self:
        abstained = self.support is PuritySupport.ABSTAINED
        if abstained != (self.estimate is None):
            raise ValueError("abstained support must omit the purity estimate")
        if abstained != (self.explanation is None):
            raise ValueError("abstained support must omit the local explanation")
        if abstained and not self.abstention_reasons:
            raise ValueError("abstained results require reasons")
        if not abstained and self.abstention_reasons:
            raise ValueError("estimated results cannot carry abstention reasons")
        return self


class UnverifiedGbmRnaPurityResult(_GbmRnaPurityResultDocument):
    """Structurally valid result whose self digest has not yet been trusted."""


class GbmRnaPurityResult(_GbmRnaPurityResultDocument):
    @model_validator(mode="after")
    def result_digest_is_valid(self) -> Self:
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result_digest does not match the result payload")
        return self


class GbmRnaPurityLimits(FrozenModel):
    model_feature_count: int = 5_829
    maximum_input_genes: int = 40_000
    minimum_model_gene_coverage: float = 0.80
    supported_model_gene_coverage: float = 0.99
    maximum_request_bytes: int = 4_194_304
    maximum_result_bytes: int = 2_097_152
    maximum_replay_bytes: int = 8_388_608
    top_attribution_limit: int = 20


class GbmRnaPurityAlgorithmConstants(FrozenModel):
    preprocessing_scale: float = 10_000.0
    hidden_layer_sizes: tuple[Literal[32], Literal[16]] = (32, 16)
    input_dropout_probability_training_only: float = 0.4
    inference_dropout_active: Literal[False] = False
    output_clipping_lower: float = 0.0
    output_clipping_upper: float = 1.0
    inference_dtype: Literal["float32"] = "float32"
    quantization_decimals: Literal[8] = 8
    attribution_method: Literal["exact_active_relu_path_decomposition"] = (
        "exact_active_relu_path_decomposition"
    )


class GbmRnaPurityProfile(FrozenModel):
    schema_version: Literal["glio-proteogen.gbm-rna-purity-profile/1.0.0"] = (
        "glio-proteogen.gbm-rna-purity-profile/1.0.0"
    )
    algorithm_id: Literal["gbm-rna-tumor-purity"] = "gbm-rna-tumor-purity"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["gbm-rna-tumor-purity/1.0.0"] = "gbm-rna-tumor-purity/1.0.0"
    model_id: Literal["gbmpurity-primary-idhwt-rna/1.0.0"] = "gbmpurity-primary-idhwt-rna/1.0.0"
    profile_digest: Sha256Digest
    constants: GbmRnaPurityAlgorithmConstants
    limits: GbmRnaPurityLimits
    numpy_version: NonEmptyStr
    converted_artifact_digest: Sha256Digest
    converted_artifact_file_sha256: Sha256Digest
    feature_order_digest: Sha256Digest
    weight_tensor_digest: Sha256Digest
    computational_source_digest: Sha256Digest
    demo_request_digest: Sha256Digest
    source_repository: Literal["https://github.com/scmpht/GBMPurity"]
    source_commit: Literal["af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950"]
    source_model_sha256: Sha256Digest
    source_gene_lengths_sha256: Sha256Digest
    source_license: Literal["MIT"]
    source_article_doi: Literal["10.1093/neuonc/noaf026"]
    source_article_license: Literal["CC-BY-4.0"]
    intended_use: Literal[
        "research_estimation_of_malignant_cell_fraction_in_primary_IDH_wildtype_GBM_bulk_RNA"
    ]
    claim_ceiling: Literal[
        "published_model_estimate_only_not_cell_type_composition_or_clinical_truth"
    ]
    safety_class: Literal["research_use_only"]

    @model_validator(mode="after")
    def digest_is_valid(self) -> Self:
        document = self.model_dump(mode="json")
        declared = document.pop("profile_digest")
        if declared != sha256_digest(document):
            raise ValueError("profile_digest does not match profile content")
        return self


class GbmRnaPurityReplayVerificationRequest(FrozenModel):
    schema_version: Literal["glio-proteogen.gbm-rna-purity-replay-request/1.0.0"] = (
        "glio-proteogen.gbm-rna-purity-replay-request/1.0.0"
    )
    request: GbmRnaPurityRequest
    result: UnverifiedGbmRnaPurityResult | GbmRnaPurityResult


class GbmRnaPurityReplayVerificationResult(FrozenModel):
    schema_version: Literal["glio-proteogen.gbm-rna-purity-replay-result/1.0.0"] = (
        "glio-proteogen.gbm-rna-purity-replay-result/1.0.0"
    )
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    result_digest_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    provided_result_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr


def empty_result_digest() -> str:
    """Stable placeholder used only while constructing a self-digested result."""

    return sha256_digest({"gbm_rna_purity": "pending"})


def request_digest(request: GbmRnaPurityRequest) -> str:
    return canonical_request_digest(request)


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "MINIMUM_MODEL_GENE_COVERAGE",
    "MODEL_FEATURE_COUNT",
    "MODEL_ID",
    "PROFILE_ID",
    "REQUIRED_CONTEXT",
    "SUPPORTED_MODEL_GENE_COVERAGE",
    "TOP_ATTRIBUTION_LIMIT",
    "AttributionDirection",
    "ClippingState",
    "GbmRnaContextAttestation",
    "GbmRnaPurityAlgorithmConstants",
    "GbmRnaPurityDiagnostics",
    "GbmRnaPurityEstimate",
    "GbmRnaPurityLimits",
    "GbmRnaPurityProfile",
    "GbmRnaPurityProvenance",
    "GbmRnaPurityReplayVerificationRequest",
    "GbmRnaPurityReplayVerificationResult",
    "GbmRnaPurityRequest",
    "GbmRnaPurityResult",
    "GeneLocalAttribution",
    "HiddenActivationTrace",
    "LocalLinearExplanation",
    "ModelCoverage",
    "PuritySupport",
    "RawGeneCount",
    "UnverifiedGbmRnaPurityResult",
    "empty_result_digest",
    "request_digest",
]
