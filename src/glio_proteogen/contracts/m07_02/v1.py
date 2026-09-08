"""Provisional M07-02 representation and feature-constructor contracts.

The dossier requires deterministic, leakage-safe feature construction with
complete feature lineage, but it does not freeze operation names, schemas,
media types, feature catalogues, endpoints, or transformation vocabularies.
Every ABI symbol in this file is provisional scaffolding.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m07_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M07-02 dossier slice.
M0702_MODULE_ID: Final = "GLIO-PROTEOGEN-M07-02"
M0702_OPERATION: Final = "construct_proteotype_analysis_representation"
M0702_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0702_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-02+json"
M0702_PARENT: Final = "proteotype"
M0702_OWNER: Final = "Platform engineering"
M0702_SAFETY_CLASS: Final = "S2"
M0702_GATE: Final = "G1"
M0702_MAX_FEATURES: Final = 512
M0702_MAX_TRANSFORMATIONS: Final = 64
M0702_MAX_SOURCE_FIELDS: Final = 64
M0702_MAX_VALUES: Final = 4096
M0702_MAX_LEAKAGE_CHECKS: Final = 128
M0702_MAX_EVIDENCE: Final = 32
M0702_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0702_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0702_M0701_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-01+json"
M0702_MAX_TYPED_OBSERVATIONS: Final = 512
M0702_MAX_TYPED_EFFECT: Final = 20.0
M0702_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M0702_MAX_BOOTSTRAP_REPLICATES: Final = 256
M0702_GLIOMA_MODEL_FAMILY: Final = "glioma-copy-number-purity-irls/1.0.0"
M0702_MAX_DIAGNOSTICS: Final = 32
M0702_EVIDENCE_CLAIM: Final = (
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


class RepresentationConstructionStatus(StrEnum):
    CONSTRUCTED = "constructed"
    ABSTAINED = "abstained"


class GliomaCopyNumberEvidenceState(StrEnum):
    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class GliomaRepresentationOptimizationStatus(StrEnum):
    CONVERGED = "converged"
    NOT_CONVERGED = "not_converged"
    NOT_EVALUABLE = "not_evaluable"


class RepresentationTransformation(FrozenModel):
    sequence: int = Field(ge=1, le=M0702_MAX_TRANSFORMATIONS)
    kind: RepresentationTransformationKind
    name: NonEmptyStr
    parameters_digest: Sha256Digest
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)


class FeatureLineage(FrozenModel):
    """Complete source and transformation lineage for one feature."""

    feature_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0702_MAX_EVIDENCE
    )
    source_fields: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M0702_MAX_SOURCE_FIELDS
    )
    transformations: tuple[RepresentationTransformation, ...] = Field(
        min_length=1, max_length=M0702_MAX_TRANSFORMATIONS
    )
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)

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
    dimension: int = Field(ge=1, le=M0702_MAX_VALUES)
    lineage: FeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def specification_binds_lineage(self) -> FeatureSpecification:
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("feature specification must bind its exact lineage feature id")
        return self


class GliomaCopyNumberObservation(FrozenModel):
    """Purity-aware copy-number segment evidence for the research lane."""

    observation_id: Identifier
    feature_id: Identifier
    gene: NonEmptyStr
    chromosome: NonEmptyStr
    segment_start: int = Field(ge=1)
    segment_end: int = Field(ge=1)
    evidence_state: GliomaCopyNumberEvidenceState
    log2_ratio: float | None = Field(
        default=None, ge=-M0702_MAX_TYPED_EFFECT, le=M0702_MAX_TYPED_EFFECT
    )
    standard_error: float | None = Field(default=None, gt=0.0, le=M0702_MAX_TYPED_EFFECT)
    tumor_purity: float | None = Field(default=None, gt=0.0, le=1.0)
    minor_copy_number: float | None = Field(default=None, ge=0.0, le=M0702_MAX_TYPED_EFFECT)
    censoring_limit: float | None = Field(
        default=None, ge=-M0702_MAX_TYPED_EFFECT, le=M0702_MAX_TYPED_EFFECT
    )
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def observation_shape_is_closed(self) -> GliomaCopyNumberObservation:
        if self.segment_end < self.segment_start:
            raise ValueError("copy-number segment end must not precede its start")
        for name, value in (
            ("log2_ratio", self.log2_ratio),
            ("standard_error", self.standard_error),
            ("tumor_purity", self.tumor_purity),
            ("minor_copy_number", self.minor_copy_number),
            ("censoring_limit", self.censoring_limit),
            ("quality_weight", self.quality_weight),
        ):
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.evidence_state is GliomaCopyNumberEvidenceState.OBSERVED:
            if (
                self.log2_ratio is None
                or self.standard_error is None
                or self.tumor_purity is None
                or self.censoring_limit is not None
                or self.quality_weight <= 0.0
            ):
                raise ValueError("observed copy-number evidence requires ratio, error, and purity")
        elif self.evidence_state is GliomaCopyNumberEvidenceState.LEFT_CENSORED:
            if (
                self.censoring_limit is None
                or self.standard_error is None
                or self.tumor_purity is None
                or self.log2_ratio is not None
                or self.quality_weight <= 0.0
            ):
                raise ValueError(
                    "left-censored copy-number evidence requires limit, error, and purity"
                )
        elif (
            self.log2_ratio is not None
            or self.standard_error is not None
            or self.tumor_purity is not None
            or self.minor_copy_number is not None
            or self.censoring_limit is not None
            or self.quality_weight != 0.0
        ):
            raise ValueError("missing or unsupported copy-number evidence cannot carry a value")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("typed copy-number evidence must use the evidence role")
        return self


class GliomaRepresentationOptimizationDiagnostic(FrozenModel):
    """Replay-visible diagnostics for the purity-aware typed fit."""

    diagnostic_id: Identifier
    status: GliomaRepresentationOptimizationStatus
    objective: NonEmptyStr
    iteration_count: int = Field(ge=0)
    objective_value: float | None = None
    convergence_gap: float | None = Field(default=None, ge=0.0)
    objective_trace_digest: Sha256Digest | None = None
    model_family: NonEmptyStr | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def diagnostic_shape_is_closed(self) -> GliomaRepresentationOptimizationDiagnostic:
        if self.status is GliomaRepresentationOptimizationStatus.CONVERGED:
            if self.objective_value is None or self.convergence_gap is None:
                raise ValueError("converged representation diagnostic requires objective and gap")
        elif self.objective_value is not None and self.convergence_gap is None:
            raise ValueError("objective value requires a convergence gap")
        return self


class RepresentationPolicy(FrozenModel):
    """Locked scaling, masking, covariate, and leakage policy."""

    policy_id: Identifier
    version: SemanticVersion
    scaling_method: NonEmptyStr
    mask_policy: NonEmptyStr
    covariates: tuple[NonEmptyStr, ...] = Field(default=(), max_length=M0702_MAX_SOURCE_FIELDS)
    locked: Literal[True] = True
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)


class RepresentationFeature(FrozenModel):
    """Constructed aggregate feature values with their exact lineage."""

    feature_id: Identifier
    value_kind: RepresentationValueKind
    unit: NonEmptyStr
    values: tuple[float, ...] = Field(min_length=1, max_length=M0702_MAX_VALUES)
    mask: tuple[bool, ...] = Field(default=(), max_length=M0702_MAX_VALUES)
    evidence_count: int = Field(default=0, ge=0, le=M0702_MAX_TYPED_OBSERVATIONS)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    top_drivers: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    model_family: NonEmptyStr | None = None
    lineage: FeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def feature_shape_is_closed(self) -> RepresentationFeature:
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("representation feature must bind its exact lineage feature id")
        if self.mask and len(self.mask) != len(self.values):
            raise ValueError("feature mask must be empty or match value length")
        return self


class LeakageCheck(FrozenModel):
    check_id: Identifier
    status: LeakageCheckStatus
    message: NonEmptyStr
    held_out_group: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)


class ConstructProteotypeAnalysisRepresentationRequest(FrozenModel):
    """Provisional request ABI for representation and feature construction."""

    operation: Literal["construct_proteotype_analysis_representation"] = M0702_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0702_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    formal_state_result: ArtifactReference
    feature_specs: tuple[FeatureSpecification, ...] = Field(
        min_length=1, max_length=M0702_MAX_FEATURES
    )
    policy: RepresentationPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0702_MAX_EVIDENCE
    )
    typed_observations: tuple[GliomaCopyNumberObservation, ...] = Field(
        default=(), max_length=M0702_MAX_TYPED_OBSERVATIONS
    )
    max_iterations: int = Field(default=128, gt=0, le=10_000)
    bootstrap_replicates: int = Field(
        default=M0702_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M0702_MAX_BOOTSTRAP_REPLICATES,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(
        self,
    ) -> ConstructProteotypeAnalysisRepresentationRequest:
        if self.formal_state_result.media_type != M0702_M0701_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M07-01 result media type")
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
                raise ValueError("typed copy-number observation ids must be unique")
            requested_feature_ids = {item.feature_id for item in self.feature_specs}
            unknown = sorted(
                {item.feature_id for item in self.typed_observations} - requested_feature_ids
            )
            if unknown:
                raise ValueError("typed copy-number observations must reference requested features")
            segment_keys = tuple(
                (
                    item.feature_id,
                    item.gene.casefold(),
                    item.chromosome.casefold(),
                    item.segment_start,
                    item.segment_end,
                )
                for item in self.typed_observations
            )
            if len(segment_keys) != len(set(segment_keys)):
                raise ValueError("typed copy-number segments must be unique")
        return self


class ProteotypeAnalysisRepresentationResult(FrozenModel):
    """Provisional result; failed leakage checks cannot publish a representation."""

    output_type: Literal["proteotype_analysis_representation"] = (
        "proteotype_analysis_representation"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0702_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructProteotypeAnalysisRepresentationRequest
    status: RepresentationConstructionStatus
    features: tuple[RepresentationFeature, ...] = Field(
        default=(), max_length=M0702_MAX_FEATURES
    )
    leakage_checks: tuple[LeakageCheck, ...] = Field(
        default=(), max_length=M0702_MAX_LEAKAGE_CHECKS
    )
    optimization_diagnostics: tuple[GliomaRepresentationOptimizationDiagnostic, ...] = Field(
        default=(), max_length=M0702_MAX_DIAGNOSTICS
    )
    model_family: NonEmptyStr | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M0702_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0702_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeAnalysisRepresentationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        feature_ids = {item.feature_id for item in self.features}
        if feature_ids and feature_ids != {item.feature_id for item in self.request.feature_specs}:
            raise ValueError("result features must cover the requested feature specification")
        leakage_statuses = {item.status for item in self.leakage_checks}
        if self.status is RepresentationConstructionStatus.CONSTRUCTED:
            if (
                not self.features
                or self.abstention_reason is not None
                or LeakageCheckStatus.FAILED in leakage_statuses
                or LeakageCheckStatus.NOT_EVALUABLE in leakage_statuses
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("constructed result requires complete leakage-safe support")
            if {item.check_id for item in self.leakage_checks} != {
                f"leakage.{spec.feature_id}" for spec in self.request.feature_specs
            }:
                raise ValueError("constructed result requires one leakage check per feature")
        elif (
            self.features
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no features, a reason, and safe status")
        check_ids = tuple(item.check_id for item in self.leakage_checks)
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("leakage check ids must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class ConstructProteotypeAnalysisRepresentationVerification(FrozenModel):
    """Replay verdict for one canonical representation result."""

    content_verified: bool
    deterministic_verified: bool
    verified: bool
    result_digest: Sha256Digest | None = None
    reason: RepresentationReplayReason

    @model_validator(mode="after")
    def verification_is_closed(
        self,
    ) -> ConstructProteotypeAnalysisRepresentationVerification:
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
    "M0702_CONTRACT_VERSION",
    "M0702_DEFAULT_BOOTSTRAP_REPLICATES",
    "M0702_EVIDENCE_CLAIM",
    "M0702_GATE",
    "M0702_GLIOMA_MODEL_FAMILY",
    "M0702_M0701_RESULT_MEDIA_TYPE",
    "M0702_MAX_BOOTSTRAP_REPLICATES",
    "M0702_MAX_CANONICAL_REQUEST_BYTES",
    "M0702_MAX_CANONICAL_RESULT_BYTES",
    "M0702_MAX_DIAGNOSTICS",
    "M0702_MAX_EVIDENCE",
    "M0702_MAX_FEATURES",
    "M0702_MAX_LEAKAGE_CHECKS",
    "M0702_MAX_SOURCE_FIELDS",
    "M0702_MAX_TRANSFORMATIONS",
    "M0702_MAX_TYPED_EFFECT",
    "M0702_MAX_TYPED_OBSERVATIONS",
    "M0702_MAX_VALUES",
    "M0702_MODULE_ID",
    "M0702_OPERATION",
    "M0702_OUTPUT_MEDIA_TYPE",
    "M0702_OWNER",
    "M0702_PARENT",
    "M0702_SAFETY_CLASS",
    "ConstructProteotypeAnalysisRepresentationRequest",
    "ConstructProteotypeAnalysisRepresentationVerification",
    "FeatureLineage",
    "FeatureSpecification",
    "GliomaCopyNumberEvidenceState",
    "GliomaCopyNumberObservation",
    "GliomaRepresentationOptimizationDiagnostic",
    "GliomaRepresentationOptimizationStatus",
    "LeakageCheck",
    "LeakageCheckStatus",
    "ProteotypeAnalysisRepresentationResult",
    "RepresentationConstructionStatus",
    "RepresentationFeature",
    "RepresentationPolicy",
    "RepresentationReplayReason",
    "RepresentationTransformation",
    "RepresentationTransformationKind",
    "RepresentationValueKind",
]
