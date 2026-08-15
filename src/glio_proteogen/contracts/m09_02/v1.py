"""Provisional M09-02 representation and feature-constructor contracts.

The dossier requires deterministic, leakage-safe feature construction with
complete feature lineage, but does not freeze the public ABI, estimator, or
feature catalogue.  These symbols are provisional scaffolding pending review.
"""

from __future__ import annotations

from enum import StrEnum
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
    source_fields: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M0902_MAX_SOURCE_FIELDS
    )
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
    lineage: FeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def specification_binds_lineage(self) -> FeatureSpecification:
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("feature specification must bind its exact lineage feature id")
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
    def covariates_are_unique(cls, values: tuple[NonEmptyStr, ...]) -> tuple[NonEmptyStr, ...]:
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def feature_shape_is_closed(self) -> RepresentationFeature:
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("representation feature must bind its exact lineage feature id")
        if self.mask and len(self.mask) != len(self.values):
            raise ValueError("feature mask must be empty or match value length")
        if self.mask and not any(self.mask):
            raise ValueError("feature mask must retain at least one supported value")
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
    features: tuple[RepresentationFeature, ...] = Field(
        default=(), max_length=M0902_MAX_FEATURES
    )
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
    "M0902_EVIDENCE_CLAIM",
    "M0902_GATE",
    "M0902_M0901_RESULT_MEDIA_TYPE",
    "M0902_MAX_CANONICAL_REQUEST_BYTES",
    "M0902_MAX_CANONICAL_RESULT_BYTES",
    "M0902_MAX_EVIDENCE",
    "M0902_MAX_FEATURES",
    "M0902_MAX_LEAKAGE_CHECKS",
    "M0902_MAX_SOURCE_FIELDS",
    "M0902_MAX_TRANSFORMATIONS",
    "M0902_MAX_VALUES",
    "M0902_MODULE_ID",
    "M0902_OPERATION",
    "M0902_OUTPUT_MEDIA_TYPE",
    "M0902_OWNER",
    "M0902_PARENT",
    "M0902_PROVISIONAL_ABI",
    "M0902_SAFETY_CLASS",
    "ComplexActivityRepresentationResult",
    "ConstructComplexActivityRepresentationRequest",
    "FeatureLineage",
    "FeatureSpecification",
    "LeakageCheck",
    "LeakageCheckStatus",
    "RepresentationConstructionStatus",
    "RepresentationFeature",
    "RepresentationPolicy",
    "RepresentationTransformation",
    "RepresentationTransformationKind",
    "RepresentationValueKind",
]
