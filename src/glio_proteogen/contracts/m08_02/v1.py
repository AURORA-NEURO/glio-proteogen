"""Provisional M08-02 representation and feature-constructor contracts.

The dossier requires deterministic, leakage-safe feature construction with
complete feature lineage, but does not freeze the public ABI or estimator.
These symbols are explicitly provisional pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m08_02.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
)

M0802_MODULE_ID: Final = "GLIO-PROTEOGEN-M08-02"
M0802_OPERATION: Final = "construct_transcript_protein_representation"
M0802_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0802_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-02+json"
M0802_PARENT: Final = "protein_subtype"
M0802_OWNER: Final = "Scientific engineering"
M0802_SAFETY_CLASS: Final = "S2"
M0802_GATE: Final = "G1"
M0802_PROVISIONAL_ABI: Final = True
M0802_MAX_FEATURES: Final = 512
M0802_MAX_TRANSFORMATIONS: Final = 64
M0802_MAX_SOURCE_FIELDS: Final = 64
M0802_MAX_VALUES: Final = 4096
M0802_MAX_LEAKAGE_CHECKS: Final = 128
M0802_MAX_EVIDENCE: Final = 32
M0802_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0802_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0802_M0801_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-01+json"
M0802_MAX_TYPED_OBSERVATIONS: Final = 512
M0802_MAX_TYPED_EFFECT: Final = 20.0
M0802_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M0802_MAX_BOOTSTRAP_REPLICATES: Final = 256
M0802_MAX_DIAGNOSTICS: Final = 32
M0802_GLIOMA_MODEL_FAMILY: Final = "glioma-transcript-protein-discordance-irls/1.0.0"
M0802_EVIDENCE_CLAIM: Final = (
    "Caller-declared representation and feature-lineage evidence; issuer authority "
    "is not authenticated."
)


class RepresentationValueKind(StrEnum):
    SCALAR = "scalar"
    VECTOR = "vector"
    MASK = "mask"
    COVARIATE = "covariate"


class RepresentationTransformationKind(StrEnum):
    SCALING = "scaling"
    MASKING = "masking"
    COVARIATE = "covariate"
    RESIDUAL = "residual"
    NORMALIZATION = "normalization"


class LeakageCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class RepresentationReplayReason(StrEnum):
    VERIFIED = "verified"
    INVALID_RESULT = "invalid_result"
    DIGEST_MISMATCH = "digest_mismatch"
    CANONICAL_BYTES_MISMATCH = "canonical_bytes_mismatch"
    RESULT_TOO_LARGE = "result_too_large"


class RepresentationConstructionStatus(StrEnum):
    CONSTRUCTED = "constructed"
    ABSTAINED = "abstained"


class GliomaTranscriptProteinEvidenceState(StrEnum):
    """Measurement state; missing and unsupported are never negative evidence."""

    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class DiscordanceOptimizationStatus(StrEnum):
    CONVERGED = "converged"
    NOT_CONVERGED = "not_converged"
    NOT_EVALUABLE = "not_evaluable"


class GliomaTranscriptProteinObservation(FrozenModel):
    """Explicit paired transcript/protein evidence for a glioma gene."""

    observation_id: Identifier
    feature_id: Identifier
    gene: NonEmptyStr
    evidence_state: GliomaTranscriptProteinEvidenceState
    transcript_effect: float | None = Field(
        default=None, ge=-M0802_MAX_TYPED_EFFECT, le=M0802_MAX_TYPED_EFFECT
    )
    protein_effect: float | None = Field(
        default=None, ge=-M0802_MAX_TYPED_EFFECT, le=M0802_MAX_TYPED_EFFECT
    )
    transcript_standard_error: float | None = Field(
        default=None, gt=0.0, le=M0802_MAX_TYPED_EFFECT
    )
    protein_standard_error: float | None = Field(
        default=None, gt=0.0, le=M0802_MAX_TYPED_EFFECT
    )
    transcript_censoring_limit: float | None = Field(
        default=None, ge=-M0802_MAX_TYPED_EFFECT, le=M0802_MAX_TYPED_EFFECT
    )
    protein_censoring_limit: float | None = Field(
        default=None, ge=-M0802_MAX_TYPED_EFFECT, le=M0802_MAX_TYPED_EFFECT
    )
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def typed_observation_shape_is_closed(self) -> GliomaTranscriptProteinObservation:
        for name, value in (
            ("transcript_effect", self.transcript_effect),
            ("protein_effect", self.protein_effect),
            ("transcript_standard_error", self.transcript_standard_error),
            ("protein_standard_error", self.protein_standard_error),
            ("transcript_censoring_limit", self.transcript_censoring_limit),
            ("protein_censoring_limit", self.protein_censoring_limit),
            ("quality_weight", self.quality_weight),
        ):
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.evidence_state is GliomaTranscriptProteinEvidenceState.OBSERVED:
            if (
                self.transcript_effect is None
                or self.protein_effect is None
                or self.transcript_standard_error is None
                or self.protein_standard_error is None
                or self.transcript_censoring_limit is not None
                or self.protein_censoring_limit is not None
                or self.quality_weight <= 0.0
            ):
                raise ValueError(
                    "observed transcript-protein evidence requires paired effects, "
                    "errors, and quality"
                )
        elif self.evidence_state is GliomaTranscriptProteinEvidenceState.LEFT_CENSORED:
            if (
                self.transcript_standard_error is None
                or self.protein_standard_error is None
                or (self.transcript_effect is None and self.transcript_censoring_limit is None)
                or (self.protein_effect is None and self.protein_censoring_limit is None)
                or (
                    self.transcript_effect is not None
                    and self.transcript_censoring_limit is not None
                )
                or (self.protein_effect is not None and self.protein_censoring_limit is not None)
                or self.quality_weight <= 0.0
            ):
                raise ValueError(
                    "left-censored transcript-protein evidence requires paired values or limits"
                )
        elif any(
            value is not None
            for value in (
                self.transcript_effect,
                self.protein_effect,
                self.transcript_standard_error,
                self.protein_standard_error,
                self.transcript_censoring_limit,
                self.protein_censoring_limit,
            )
        ) or self.quality_weight != 0.0:
            raise ValueError(
                "missing or unsupported transcript-protein evidence cannot carry a value"
            )
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("typed transcript-protein evidence must use the evidence role")
        return self


class DiscordanceOptimizationDiagnostic(FrozenModel):
    """Replay-visible diagnostics for a typed transcript-protein fit."""

    diagnostic_id: Identifier
    status: DiscordanceOptimizationStatus
    objective: NonEmptyStr
    iteration_count: int = Field(ge=0)
    objective_value: float | None = None
    convergence_gap: float | None = Field(default=None, ge=0.0)
    objective_trace_digest: Sha256Digest | None = None
    model_family: NonEmptyStr | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def diagnostic_shape_is_closed(self) -> DiscordanceOptimizationDiagnostic:
        if self.status is DiscordanceOptimizationStatus.CONVERGED:
            if self.objective_value is None or self.convergence_gap is None:
                raise ValueError("converged diagnostic requires objective and convergence gap")
        elif self.objective_value is not None and self.convergence_gap is None:
            raise ValueError("objective value requires a convergence gap")
        return self


class RepresentationTransformation(FrozenModel):
    sequence: int = Field(ge=1, le=M0802_MAX_TRANSFORMATIONS)
    kind: RepresentationTransformationKind
    name: NonEmptyStr
    parameters_digest: Sha256Digest
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)


class FeatureLineage(FrozenModel):
    """Complete source and transformation lineage for one feature."""

    feature_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0802_MAX_EVIDENCE
    )
    source_fields: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M0802_MAX_SOURCE_FIELDS
    )
    transformations: tuple[RepresentationTransformation, ...] = Field(
        min_length=1, max_length=M0802_MAX_TRANSFORMATIONS
    )
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def transformations_are_ordered(self) -> FeatureLineage:
        sequences = tuple(item.sequence for item in self.transformations)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("feature transformations must have unique ordered sequences")
        if any(not item.leakage_safe for item in self.transformations):
            raise ValueError("feature lineage cannot contain a leakage-unsafe transformation")
        return self


class FeatureSpecification(FrozenModel):
    feature_id: Identifier
    version: SemanticVersion
    value_kind: RepresentationValueKind
    unit: NonEmptyStr
    dimension: int = Field(ge=1, le=M0802_MAX_VALUES)
    source_values: tuple[float, ...] = Field(default=(), max_length=M0802_MAX_VALUES)
    lineage: FeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def specification_binds_lineage(self) -> FeatureSpecification:
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("feature specification must bind its exact lineage feature id")
        if self.source_values and len(self.source_values) != self.dimension:
            raise ValueError("source values must match the declared feature dimension")
        if any(not isfinite(value) for value in self.source_values):
            raise ValueError("source values must be finite")
        return self


class RepresentationPolicy(FrozenModel):
    """Locked scaling, masking, covariate, and leakage policy."""

    policy_id: Identifier
    version: SemanticVersion
    scaling_method: NonEmptyStr
    mask_policy: NonEmptyStr
    covariates: tuple[NonEmptyStr, ...] = Field(default=(), max_length=M0802_MAX_SOURCE_FIELDS)
    locked: Literal[True] = True
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)


class RepresentationFeature(FrozenModel):
    """Constructed feature values with their exact immutable lineage."""

    feature_id: Identifier
    value_kind: RepresentationValueKind
    unit: NonEmptyStr
    values: tuple[float, ...] = Field(min_length=1, max_length=M0802_MAX_VALUES)
    mask: tuple[bool, ...] = Field(default=(), max_length=M0802_MAX_VALUES)
    lineage: FeatureLineage
    evidence_count: int = Field(default=0, ge=0, le=M0802_MAX_TYPED_OBSERVATIONS)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    top_drivers: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    ablation_effects: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    lower_bound: float | None = Field(
        default=None, ge=-M0802_MAX_TYPED_EFFECT, le=M0802_MAX_TYPED_EFFECT
    )
    upper_bound: float | None = Field(
        default=None, ge=-M0802_MAX_TYPED_EFFECT, le=M0802_MAX_TYPED_EFFECT
    )
    model_family: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def feature_shape_is_closed(self) -> RepresentationFeature:
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("representation feature must bind its exact lineage feature id")
        if self.mask and len(self.mask) != len(self.values):
            raise ValueError("feature mask must be empty or match value length")
        if (self.lower_bound is None) != (self.upper_bound is None):
            raise ValueError("feature interval requires both bounds")
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and (
                self.lower_bound > self.upper_bound
                or not self.lower_bound <= self.values[0] <= self.upper_bound
            )
        ):
            raise ValueError("feature interval must contain the first value")
        return self


class LeakageCheck(FrozenModel):
    check_id: Identifier
    status: LeakageCheckStatus
    message: NonEmptyStr
    held_out_group: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)


class ConstructTranscriptProteinRepresentationRequest(FrozenModel):
    """Provisional request ABI for representation and feature construction."""

    operation: Literal["construct_transcript_protein_representation"] = M0802_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0802_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    formal_state_result: ArtifactReference
    feature_specs: tuple[FeatureSpecification, ...] = Field(
        min_length=1, max_length=M0802_MAX_FEATURES
    )
    policy: RepresentationPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0802_MAX_EVIDENCE
    )
    typed_observations: tuple[GliomaTranscriptProteinObservation, ...] = Field(
        default=(), max_length=M0802_MAX_TYPED_OBSERVATIONS
    )
    max_iterations: int = Field(default=128, gt=0, le=10_000)
    bootstrap_replicates: int = Field(
        default=M0802_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M0802_MAX_BOOTSTRAP_REPLICATES,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ConstructTranscriptProteinRepresentationRequest:
        if self.formal_state_result.media_type != M0802_M0801_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M08-01 result media type")
        feature_ids = tuple(item.feature_id for item in self.feature_specs)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("feature specification ids must be unique")
        if any(
            artifact.artifact_id == self.formal_state_result.artifact_id
            for artifact in self.source_artifacts
        ):
            raise ValueError("formal-state handoff must not be duplicated as a source artifact")
        if self.typed_observations:
            observation_ids = tuple(item.observation_id for item in self.typed_observations)
            if len(observation_ids) != len(set(observation_ids)):
                raise ValueError("typed transcript-protein observation identifiers must be unique")
            typed_feature_ids = {item.feature_id for item in self.feature_specs}
            if any(
                item.feature_id not in typed_feature_ids for item in self.typed_observations
            ):
                raise ValueError(
                    "typed transcript-protein observations must bind requested features"
                )
            gene_keys = tuple((item.feature_id, item.gene) for item in self.typed_observations)
            if len(gene_keys) != len(set(gene_keys)):
                raise ValueError("typed transcript-protein genes must be unique per feature")
        return self


class TranscriptProteinRepresentationResult(FrozenModel):
    """Provisional result; failed leakage checks cannot publish a representation."""

    output_type: Literal["transcript_protein_representation"] = (
        "transcript_protein_representation"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0802_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructTranscriptProteinRepresentationRequest
    status: RepresentationConstructionStatus
    features: tuple[RepresentationFeature, ...] = Field(
        default=(), max_length=M0802_MAX_FEATURES
    )
    optimization_diagnostics: tuple[DiscordanceOptimizationDiagnostic, ...] = Field(
        default=(), max_length=M0802_MAX_DIAGNOSTICS
    )
    model_family: NonEmptyStr | None = None
    leakage_checks: tuple[LeakageCheck, ...] = Field(
        default=(), max_length=M0802_MAX_LEAKAGE_CHECKS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M0802_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> TranscriptProteinRepresentationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        feature_ids = tuple(item.feature_id for item in self.features)
        expected_feature_ids = tuple(item.feature_id for item in self.request.feature_specs)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("result feature ids must be unique")
        if feature_ids and set(feature_ids) != set(expected_feature_ids):
            raise ValueError("result features must cover the requested feature specification")
        check_ids = tuple(item.check_id for item in self.leakage_checks)
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("leakage check ids must be unique")
        optimization_ids = tuple(item.diagnostic_id for item in self.optimization_diagnostics)
        if len(optimization_ids) != len(set(optimization_ids)):
            raise ValueError("optimization diagnostic ids must be unique")
        leakage_statuses = {item.status for item in self.leakage_checks}
        if self.status is RepresentationConstructionStatus.CONSTRUCTED:
            if (
                not self.features
                or self.abstention_reason is not None
                or LeakageCheckStatus.FAILED in leakage_statuses
                or LeakageCheckStatus.NOT_EVALUABLE in leakage_statuses
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or set(feature_ids) != set(expected_feature_ids)
                or set(check_ids)
                != {f"leakage.{feature_id}" for feature_id in expected_feature_ids}
            ):
                raise ValueError("constructed result requires complete leakage-safe support")
        elif (
            self.features
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no features, a reason, and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class ConstructTranscriptProteinRepresentationVerification(FrozenModel):
    """Replay verdict for one canonical representation result."""

    content_verified: bool
    deterministic_verified: bool
    verified: bool
    result_digest: Sha256Digest | None = None
    reason: RepresentationReplayReason

    @model_validator(mode="after")
    def verification_is_closed(
        self,
    ) -> ConstructTranscriptProteinRepresentationVerification:
        if self.verified != (self.content_verified and self.deterministic_verified):
            raise ValueError("verified must equal content and deterministic verification")
        if self.verified and self.reason is not RepresentationReplayReason.VERIFIED:
            raise ValueError("verified replay requires verified reason")
        if not self.verified and self.result_digest is not None:
            raise ValueError("failed replay cannot expose a trusted result digest")
        if self.verified and self.result_digest is None:
            raise ValueError("verified replay requires a result digest")
        return self


__all__ = [
    "M0802_CONTRACT_VERSION",
    "M0802_DEFAULT_BOOTSTRAP_REPLICATES",
    "M0802_EVIDENCE_CLAIM",
    "M0802_GATE",
    "M0802_GLIOMA_MODEL_FAMILY",
    "M0802_M0801_RESULT_MEDIA_TYPE",
    "M0802_MAX_BOOTSTRAP_REPLICATES",
    "M0802_MAX_CANONICAL_REQUEST_BYTES",
    "M0802_MAX_CANONICAL_RESULT_BYTES",
    "M0802_MAX_DIAGNOSTICS",
    "M0802_MAX_EVIDENCE",
    "M0802_MAX_FEATURES",
    "M0802_MAX_LEAKAGE_CHECKS",
    "M0802_MAX_SOURCE_FIELDS",
    "M0802_MAX_TRANSFORMATIONS",
    "M0802_MAX_TYPED_EFFECT",
    "M0802_MAX_TYPED_OBSERVATIONS",
    "M0802_MAX_VALUES",
    "M0802_MODULE_ID",
    "M0802_OPERATION",
    "M0802_OUTPUT_MEDIA_TYPE",
    "M0802_OWNER",
    "M0802_PARENT",
    "M0802_PROVISIONAL_ABI",
    "M0802_SAFETY_CLASS",
    "ConstructTranscriptProteinRepresentationRequest",
    "ConstructTranscriptProteinRepresentationVerification",
    "DiscordanceOptimizationDiagnostic",
    "DiscordanceOptimizationStatus",
    "FeatureLineage",
    "FeatureSpecification",
    "GliomaTranscriptProteinEvidenceState",
    "GliomaTranscriptProteinObservation",
    "LeakageCheck",
    "LeakageCheckStatus",
    "RepresentationConstructionStatus",
    "RepresentationFeature",
    "RepresentationPolicy",
    "RepresentationReplayReason",
    "RepresentationTransformation",
    "RepresentationTransformationKind",
    "RepresentationValueKind",
    "TranscriptProteinRepresentationResult",
]
