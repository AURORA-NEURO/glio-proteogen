"""Provisional M09-02 representation and feature-constructor contracts.

The dossier requires deterministic, leakage-safe feature construction with
complete feature lineage, but does not freeze the public ABI, estimator, or
feature catalogue.  These symbols are provisional scaffolding pending review.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from glio_proteogen.contracts.m09_02.canonical import (
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

M0902_MODULE_ID: Final = "GLIO-PROTEOGEN-M09-02"
M0902_OPERATION: Final = "construct_complex_activity_representation"
M0902_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0902_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-02+json"
M0902_PARENT: Final = "complex_activity"
M0902_OWNER: Final = "Computational biology"
M0902_SAFETY_CLASS: Final = "S2"
M0902_GATE: Final = "G1"
M0902_PROVISIONAL_ABI: Final = True
M0902_MAX_FEATURES: Final = 1_024
M0902_MAX_TRANSFORMATIONS: Final = 128
M0902_MAX_SOURCE_FIELDS: Final = 128
M0902_MAX_VALUES: Final = 4_096
M0902_MAX_LEAKAGE_CHECKS: Final = 256
M0902_MAX_EVIDENCE: Final = 64
M0902_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0902_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0902_M0901_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-01+json"
M0902_MAX_TYPED_OBSERVATIONS: Final = 512
M0902_MAX_TYPED_EFFECT: Final = 20.0
M0902_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M0902_MAX_BOOTSTRAP_REPLICATES: Final = 256
M0902_MAX_DIAGNOSTICS: Final = 32
M0902_GLIOMA_MODEL_FAMILY: Final = "glioma-complex-stoichiometric-irls/1.0.0"
M0902_EVIDENCE_CLAIM: Final = (
    "Caller-declared complex-activity representation and feature-lineage evidence; "
    "issuer authority is not authenticated."
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


class RepresentationConstructionStatus(StrEnum):
    CONSTRUCTED = "constructed"
    ABSTAINED = "abstained"


class GliomaComplexEvidenceState(StrEnum):
    """Measurement state; missing and unsupported are never negative evidence."""

    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class ComplexOptimizationStatus(StrEnum):
    CONVERGED = "converged"
    NOT_CONVERGED = "not_converged"
    NOT_EVALUABLE = "not_evaluable"


class GliomaComplexObservation(FrozenModel):
    """Explicit member-level evidence for a glioma protein complex."""

    observation_id: Identifier
    feature_id: Identifier
    complex_id: Identifier
    member_id: Identifier
    stoichiometric_weight: float = Field(gt=0.0, le=100.0)
    essential: bool = False
    evidence_state: GliomaComplexEvidenceState
    standardized_effect: float | None = Field(
        default=None, ge=-M0902_MAX_TYPED_EFFECT, le=M0902_MAX_TYPED_EFFECT
    )
    standard_error: float | None = Field(default=None, gt=0.0, le=M0902_MAX_TYPED_EFFECT)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    censoring_limit: float | None = Field(
        default=None, ge=-M0902_MAX_TYPED_EFFECT, le=M0902_MAX_TYPED_EFFECT
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def typed_observation_shape_is_closed(self) -> GliomaComplexObservation:
        for name, value in (
            ("stoichiometric_weight", self.stoichiometric_weight),
            ("standardized_effect", self.standardized_effect),
            ("standard_error", self.standard_error),
            ("quality_weight", self.quality_weight),
            ("censoring_limit", self.censoring_limit),
        ):
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.evidence_state is GliomaComplexEvidenceState.OBSERVED:
            if (
                self.standardized_effect is None
                or self.standard_error is None
                or self.censoring_limit is not None
                or self.quality_weight <= 0.0
            ):
                raise ValueError(
                    "observed complex evidence requires effect, standard error, and quality"
                )
        elif self.evidence_state is GliomaComplexEvidenceState.LEFT_CENSORED:
            if (
                self.censoring_limit is None
                or self.standard_error is None
                or self.standardized_effect is not None
                or self.quality_weight <= 0.0
            ):
                raise ValueError(
                    "left-censored complex evidence requires limit, standard error, and quality"
                )
        elif (
            self.standardized_effect is not None
            or self.standard_error is not None
            or self.censoring_limit is not None
            or self.quality_weight != 0.0
        ):
            raise ValueError("missing or unsupported complex evidence cannot carry a value")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("typed complex evidence must use the evidence role")
        return self


class ComplexOptimizationDiagnostic(FrozenModel):
    """Replay-visible diagnostics for a typed complex activity fit."""

    diagnostic_id: Identifier
    status: ComplexOptimizationStatus
    objective: NonEmptyStr
    iteration_count: int = Field(ge=0)
    objective_value: float | None = None
    convergence_gap: float | None = Field(default=None, ge=0.0)
    objective_trace_digest: Sha256Digest | None = None
    model_family: NonEmptyStr | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def diagnostic_shape_is_closed(self) -> ComplexOptimizationDiagnostic:
        if self.status is ComplexOptimizationStatus.CONVERGED:
            if self.objective_value is None or self.convergence_gap is None:
                raise ValueError("converged diagnostic requires objective and convergence gap")
        elif self.objective_value is not None and self.convergence_gap is None:
            raise ValueError("objective value requires a convergence gap")
        return self


class RepresentationTransformation(FrozenModel):
    sequence: int = Field(ge=1, le=M0902_MAX_TRANSFORMATIONS)
    kind: RepresentationTransformationKind
    name: NonEmptyStr
    parameters_digest: Sha256Digest
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)


class FeatureLineage(FrozenModel):
    """Complete source and transformation lineage for one feature."""

    feature_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0902_MAX_EVIDENCE
    )
    source_fields: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M0902_MAX_SOURCE_FIELDS)
    transformations: tuple[RepresentationTransformation, ...] = Field(
        min_length=1, max_length=M0902_MAX_TRANSFORMATIONS
    )
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def transformations_are_ordered(self) -> FeatureLineage:
        sequences = tuple(item.sequence for item in self.transformations)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("feature transformations must have unique ordered sequences")
        if any(not item.leakage_safe for item in self.transformations):
            raise ValueError("feature lineage cannot contain a leakage-unsafe transformation")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("feature lineage source artifacts must be unique")
        fields = tuple(self.source_fields)
        if len(fields) != len(set(fields)):
            raise ValueError("feature lineage source fields must be unique")
        return self


class FeatureSpecification(FrozenModel):
    feature_id: Identifier
    version: SemanticVersion
    value_kind: RepresentationValueKind
    unit: NonEmptyStr
    dimension: int = Field(ge=1, le=M0902_MAX_VALUES)
    source_values: tuple[float, ...] = Field(default=(), max_length=M0902_MAX_VALUES)
    lineage: FeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

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
    covariates: tuple[NonEmptyStr, ...] = Field(default=(), max_length=M0902_MAX_SOURCE_FIELDS)
    locked: Literal[True] = True
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

    @field_validator("covariates")
    @classmethod
    def covariates_are_unique(
        cls, values: tuple[NonEmptyStr, ...]
    ) -> tuple[NonEmptyStr, ...]:
        _ = cls
        if len(values) != len(set(values)):
            raise ValueError("representation policy covariates must be unique")
        return tuple(sorted(values))


class RepresentationFeature(FrozenModel):
    """Constructed feature values with exact immutable lineage."""

    feature_id: Identifier
    value_kind: RepresentationValueKind
    unit: NonEmptyStr
    values: tuple[float, ...] = Field(min_length=1, max_length=M0902_MAX_VALUES)
    mask: tuple[bool, ...] = Field(default=(), max_length=M0902_MAX_VALUES)
    lineage: FeatureLineage
    evidence_count: int = Field(default=0, ge=0, le=M0902_MAX_TYPED_OBSERVATIONS)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    top_drivers: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    ablation_effects: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    lower_bound: float | None = Field(
        default=None, ge=-M0902_MAX_TYPED_EFFECT, le=M0902_MAX_TYPED_EFFECT
    )
    upper_bound: float | None = Field(
        default=None, ge=-M0902_MAX_TYPED_EFFECT, le=M0902_MAX_TYPED_EFFECT
    )
    model_family: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def feature_shape_is_closed(self) -> RepresentationFeature:
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("representation feature must bind its exact lineage feature id")
        if self.mask and len(self.mask) != len(self.values):
            raise ValueError("feature mask must be empty or match value length")
        if self.mask and not any(self.mask):
            raise ValueError("feature mask must retain at least one supported value")
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def failed_check_requires_context(self) -> LeakageCheck:
        if self.status is LeakageCheckStatus.FAILED and self.held_out_group is None:
            raise ValueError("failed leakage check requires the affected held-out group")
        return self


class ConstructComplexActivityRepresentationRequest(FrozenModel):
    """Provisional request ABI for complex-activity feature construction."""

    operation: Literal["construct_complex_activity_representation"] = M0902_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0902_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    formal_state_result: ArtifactReference
    feature_specs: tuple[FeatureSpecification, ...] = Field(
        min_length=1, max_length=M0902_MAX_FEATURES
    )
    policy: RepresentationPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0902_MAX_EVIDENCE
    )
    typed_observations: tuple[GliomaComplexObservation, ...] = Field(
        default=(), max_length=M0902_MAX_TYPED_OBSERVATIONS
    )
    max_iterations: int = Field(default=128, gt=0, le=10_000)
    bootstrap_replicates: int = Field(
        default=M0902_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M0902_MAX_BOOTSTRAP_REPLICATES,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ConstructComplexActivityRepresentationRequest:
        if self.formal_state_result.media_type != M0902_M0901_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M09-01 result media type")
        feature_ids = tuple(item.feature_id for item in self.feature_specs)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("feature specification ids must be unique")
        if any(
            artifact.artifact_id == self.formal_state_result.artifact_id
            for artifact in self.source_artifacts
        ):
            raise ValueError("formal-state handoff must not be duplicated as a source artifact")
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("request source artifacts must be unique")
        lineage_ids = tuple(item.feature_id for item in self.feature_specs)
        if any(item.lineage.feature_id not in lineage_ids for item in self.feature_specs):
            raise ValueError("every feature lineage must bind a requested feature")
        if self.typed_observations:
            observation_ids = tuple(item.observation_id for item in self.typed_observations)
            if len(observation_ids) != len(set(observation_ids)):
                raise ValueError("typed complex observation identifiers must be unique")
            typed_feature_ids = {item.feature_id for item in self.feature_specs}
            if any(item.feature_id not in typed_feature_ids for item in self.typed_observations):
                raise ValueError("typed complex observations must bind requested features")
            member_keys = tuple(
                (item.feature_id, item.complex_id, item.member_id)
                for item in self.typed_observations
            )
            if len(member_keys) != len(set(member_keys)):
                raise ValueError("typed complex member evidence must be unique per member")
        return self


class ComplexActivityRepresentationResult(FrozenModel):
    """Provisional result; failed leakage checks cannot publish features."""

    output_type: Literal["complex_activity_representation"] = "complex_activity_representation"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0902_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructComplexActivityRepresentationRequest
    status: RepresentationConstructionStatus
    features: tuple[RepresentationFeature, ...] = Field(default=(), max_length=M0902_MAX_FEATURES)
    optimization_diagnostics: tuple[ComplexOptimizationDiagnostic, ...] = Field(
        default=(), max_length=M0902_MAX_DIAGNOSTICS
    )
    model_family: NonEmptyStr | None = None
    leakage_checks: tuple[LeakageCheck, ...] = Field(
        default=(), max_length=M0902_MAX_LEAKAGE_CHECKS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M0902_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityRepresentationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        requested_ids = {item.feature_id for item in self.request.feature_specs}
        feature_ids = {item.feature_id for item in self.features}
        if feature_ids and feature_ids != requested_ids:
            raise ValueError("result features must cover the requested feature specification")
        if len(feature_ids) != len(self.features):
            raise ValueError("result feature ids must be unique")
        check_ids = tuple(item.check_id for item in self.leakage_checks)
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("result leakage check ids must be unique")
        optimization_ids = tuple(item.diagnostic_id for item in self.optimization_diagnostics)
        if len(optimization_ids) != len(set(optimization_ids)):
            raise ValueError("result optimization diagnostic ids must be unique")
        leakage_statuses = {item.status for item in self.leakage_checks}
        if self.status is RepresentationConstructionStatus.CONSTRUCTED:
            if (
                feature_ids != requested_ids
                or self.abstention_reason is not None
                or not self.leakage_checks
                or LeakageCheckStatus.FAILED in leakage_statuses
                or LeakageCheckStatus.NOT_EVALUABLE in leakage_statuses
                or self.support_decision.status is not SupportStatus.SUPPORTED
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


__all__ = [
    "M0902_CONTRACT_VERSION",
    "M0902_DEFAULT_BOOTSTRAP_REPLICATES",
    "M0902_EVIDENCE_CLAIM",
    "M0902_GATE",
    "M0902_GLIOMA_MODEL_FAMILY",
    "M0902_M0901_RESULT_MEDIA_TYPE",
    "M0902_MAX_BOOTSTRAP_REPLICATES",
    "M0902_MAX_CANONICAL_REQUEST_BYTES",
    "M0902_MAX_CANONICAL_RESULT_BYTES",
    "M0902_MAX_DIAGNOSTICS",
    "M0902_MAX_EVIDENCE",
    "M0902_MAX_FEATURES",
    "M0902_MAX_LEAKAGE_CHECKS",
    "M0902_MAX_SOURCE_FIELDS",
    "M0902_MAX_TRANSFORMATIONS",
    "M0902_MAX_TYPED_EFFECT",
    "M0902_MAX_TYPED_OBSERVATIONS",
    "M0902_MAX_VALUES",
    "M0902_MODULE_ID",
    "M0902_OPERATION",
    "M0902_OUTPUT_MEDIA_TYPE",
    "M0902_OWNER",
    "M0902_PARENT",
    "M0902_PROVISIONAL_ABI",
    "M0902_SAFETY_CLASS",
    "ComplexActivityRepresentationResult",
    "ComplexOptimizationDiagnostic",
    "ComplexOptimizationStatus",
    "ConstructComplexActivityRepresentationRequest",
    "FeatureLineage",
    "FeatureSpecification",
    "GliomaComplexEvidenceState",
    "GliomaComplexObservation",
    "LeakageCheck",
    "LeakageCheckStatus",
    "RepresentationConstructionStatus",
    "RepresentationFeature",
    "RepresentationPolicy",
    "RepresentationTransformation",
    "RepresentationTransformationKind",
    "RepresentationValueKind",
]
