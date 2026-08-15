"""Provisional M06-02 representation and feature-constructor contracts.

The dossier freezes behavior and safety boundaries, but not a public ABI.  All
operation names, field names, media types, limits, and schema names in this file
are provisional and must be reviewed before any external adapter is added.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m06_02.canonical import result_payload_digest
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

M0602_MODULE_ID: Final = "GLIO-PROTEOGEN-M06-02"
M0602_OPERATION: Final = "construct_protein_representation"
M0602_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0602_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m06-02+json"
M0602_PARENT: Final = "biomarker_panel"
M0602_OWNER: Final = "Data engineering"
M0602_SAFETY_CLASS: Final = "S2"
M0602_GATE: Final = "G1"
M0602_PROVISIONAL_ABI: Final = True

# Provisional capacities only; no release or benchmark commitment is implied.
M0602_MAX_FEATURES: Final = 512
M0602_MAX_LINEAGE_STEPS: Final = 512
M0602_MAX_MASKS: Final = 512
M0602_MAX_COVARIATES: Final = 128
M0602_MAX_EVIDENCE: Final = 64
M0602_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0602_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class RepresentationFeatureKind(StrEnum):
    SCALAR = "scalar"
    VECTOR = "vector"
    CATEGORICAL = "categorical"
    EMBEDDING = "embedding"


class RepresentationObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class RepresentationConstructorStatus(StrEnum):
    CONSTRUCTED = "constructed"
    ABSTAINED = "abstained"
    QUARANTINED = "quarantined"


class FeatureLineageRole(StrEnum):
    SOURCE = "source"
    TRANSFORM = "transform"
    AGGREGATE = "aggregate"
    MASK = "mask"


class FeatureLineageStep(FrozenModel):
    """One leakage-safe transformation receipt for a representation feature."""

    lineage_id: Identifier
    role: FeatureLineageRole
    operation: NonEmptyStr
    transformation_version: SemanticVersion
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=64)
    output_feature_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0602_MAX_FEATURES
    )
    leakage_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0602_MAX_EVIDENCE)

    @field_validator("output_feature_ids")
    @classmethod
    def output_ids_are_unique(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("lineage output feature ids must be unique")
        return tuple(sorted(values))


class RepresentationFeature(FrozenModel):
    """A value with explicit missingness and a bound lineage step."""

    feature_id: Identifier
    version: SemanticVersion
    kind: RepresentationFeatureKind
    state: RepresentationObservationState
    unit: NonEmptyStr
    lineage_id: Identifier
    source_digest: Sha256Digest
    scalar_value: float | None = None
    vector: tuple[float, ...] = Field(default=(), max_length=4096)
    category: NonEmptyStr | None = None

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> RepresentationFeature:
        present = sum(
            (
                self.scalar_value is not None,
                bool(self.vector),
                self.category is not None,
            )
        )
        if self.state is RepresentationObservationState.OBSERVED:
            if present != 1:
                raise ValueError("observed feature requires exactly one value representation")
            if self.kind is RepresentationFeatureKind.SCALAR and self.scalar_value is None:
                raise ValueError("scalar feature requires scalar_value")
            if self.kind in {
                RepresentationFeatureKind.VECTOR,
                RepresentationFeatureKind.EMBEDDING,
            } and not self.vector:
                raise ValueError("vector or embedding feature requires vector")
            if self.kind is RepresentationFeatureKind.CATEGORICAL and self.category is None:
                raise ValueError("categorical feature requires category")
        elif present:
            raise ValueError("non-observed feature cannot carry a value representation")
        return self


class RepresentationMask(FrozenModel):
    """Explicit mask receipt; missingness never becomes a negative finding."""

    feature_id: Identifier
    state: RepresentationObservationState
    reason: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0602_MAX_EVIDENCE)


class RepresentationCovariate(FrozenModel):
    covariate_id: Identifier
    version: SemanticVersion
    unit: NonEmptyStr
    value: float | NonEmptyStr
    source_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0602_MAX_EVIDENCE)


class BuildProteinRepresentationRequest(FrozenModel):
    """Provisional request for deterministic, leakage-safe feature construction."""

    operation: Literal["construct_protein_representation"] = M0602_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0602_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0602_MAX_EVIDENCE
    )
    features: tuple[RepresentationFeature, ...] = Field(
        min_length=1, max_length=M0602_MAX_FEATURES
    )
    lineage: tuple[FeatureLineageStep, ...] = Field(
        min_length=1, max_length=M0602_MAX_LINEAGE_STEPS
    )
    masks: tuple[RepresentationMask, ...] = Field(default=(), max_length=M0602_MAX_MASKS)
    covariates: tuple[RepresentationCovariate, ...] = Field(
        default=(), max_length=M0602_MAX_COVARIATES
    )
    configuration_digest: Sha256Digest
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def feature_lineage_is_closed(self) -> BuildProteinRepresentationRequest:
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("representation feature ids must be unique")
        lineage_ids = {item.lineage_id for item in self.lineage}
        if any(item.lineage_id not in lineage_ids for item in self.features):
            raise ValueError("every feature must bind to a lineage step")
        if any(item.feature_id not in set(feature_ids) for item in self.masks):
            raise ValueError("mask references an unknown feature")
        if len({item.covariate_id for item in self.covariates}) != len(self.covariates):
            raise ValueError("covariate ids must be unique")
        source_digests = {item.digest for item in self.source_artifacts}
        if any(item.source_digest not in source_digests for item in self.features):
            raise ValueError("feature source digest is not declared in source_artifacts")
        return self


class ConstructProteinRepresentationResult(FrozenModel):
    """Provisional result carrying lineage, support, uncertainty, and safety flags."""

    output_type: Literal["protein_representation"] = "protein_representation"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0602_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    status: RepresentationConstructorStatus
    features: tuple[RepresentationFeature, ...] = Field(
        min_length=1, max_length=M0602_MAX_FEATURES
    )
    lineage: tuple[FeatureLineageStep, ...] = Field(
        min_length=1, max_length=M0602_MAX_LINEAGE_STEPS
    )
    masks: tuple[RepresentationMask, ...] = Field(default=(), max_length=M0602_MAX_MASKS)
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0602_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    parent_target: Literal["biomarker_panel"] = M0602_PARENT
    emits_parent: Literal[False] = False
    infers_identity: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    leakage_checked: Literal[True] = True
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def result_digest_is_closed(self) -> ConstructProteinRepresentationResult:
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        if self.status is RepresentationConstructorStatus.CONSTRUCTED:
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("constructed result requires supported status")
        elif self.support_decision.status is SupportStatus.SUPPORTED:
            raise ValueError("abstained or quarantined result cannot claim supported status")
        return self


__all__ = [
    "M0602_CONTRACT_VERSION",
    "M0602_EVIDENCE_CLAIM",
    "M0602_GATE",
    "M0602_MAX_CANONICAL_REQUEST_BYTES",
    "M0602_MAX_CANONICAL_RESULT_BYTES",
    "M0602_MAX_COVARIATES",
    "M0602_MAX_EVIDENCE",
    "M0602_MAX_FEATURES",
    "M0602_MAX_LINEAGE_STEPS",
    "M0602_MAX_MASKS",
    "M0602_MODULE_ID",
    "M0602_OPERATION",
    "M0602_OUTPUT_MEDIA_TYPE",
    "M0602_OWNER",
    "M0602_PARENT",
    "M0602_PROVISIONAL_ABI",
    "M0602_SAFETY_CLASS",
    "BuildProteinRepresentationRequest",
    "ConstructProteinRepresentationResult",
    "FeatureLineageRole",
    "FeatureLineageStep",
    "RepresentationConstructorStatus",
    "RepresentationCovariate",
    "RepresentationFeature",
    "RepresentationFeatureKind",
    "RepresentationMask",
    "RepresentationObservationState",
]


M0602_EVIDENCE_CLAIM: Final = (
    "Caller-declared representation and feature-lineage evidence; "
    "issuer authority is not authenticated."
)
