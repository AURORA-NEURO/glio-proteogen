"""Provisional M08-02 representation and feature-constructor contracts.

The dossier requires deterministic, leakage-safe feature construction with
complete feature lineage, but does not freeze the public ABI or estimator.
These symbols are explicitly provisional pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
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
    lineage: FeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0802_MAX_EVIDENCE)

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
    "M0802_EVIDENCE_CLAIM",
    "M0802_GATE",
    "M0802_M0801_RESULT_MEDIA_TYPE",
    "M0802_MAX_CANONICAL_REQUEST_BYTES",
    "M0802_MAX_CANONICAL_RESULT_BYTES",
    "M0802_MAX_EVIDENCE",
    "M0802_MAX_FEATURES",
    "M0802_MAX_LEAKAGE_CHECKS",
    "M0802_MAX_SOURCE_FIELDS",
    "M0802_MAX_TRANSFORMATIONS",
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
    "FeatureLineage",
    "FeatureSpecification",
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
