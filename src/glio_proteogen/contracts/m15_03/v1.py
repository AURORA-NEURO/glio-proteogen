"""Provisional M15-03 mechanistic feature constructor contracts.

The dossier requires interpretable pathway, topology, state, lineage, kinetics,
spatial, or regulatory features tied to the complex-activity parent.  The ABI is
not frozen; this contract retains units, topology/perturbation invariants,
source evidence, uncertainty, and safe abstention.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m15_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 5164-5207.
M1503_MODULE_ID: Final = "GLIO-PROTEOGEN-M15-03"
M1503_OPERATION: Final = "construct_complex_activity_mechanistic_features"
M1503_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1503_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-03+json"
M1503_M1502_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-02+json"
M1503_PARENT: Final = "complex_activity"
M1503_OWNER: Final = "Scientific engineering"
M1503_SAFETY_CLASS: Final = "S2"
M1503_GATE: Final = "G1"
M1503_PROVISIONAL_ABI: Final = True
M1503_MAX_FEATURES: Final = 512
M1503_MAX_EVIDENCE: Final = 64
M1503_MAX_FINDINGS: Final = 64
M1503_MAX_ASSUMPTIONS: Final = 64
M1503_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1503_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class FeatureKind(StrEnum):
    PATHWAY = "pathway"
    TOPOLOGY = "topology"
    STATE = "state"
    LINEAGE = "lineage"
    KINETICS = "kinetics"
    SPATIAL = "spatial"
    REGULATORY = "regulatory"


class FeatureSupportStatus(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    CONFLICTED = "conflicted"
    UNRESOLVED = "unresolved"
    ABSTAINED = "abstained"


class FeatureConstructorStatus(StrEnum):
    CONSTRUCTED = "constructed"
    ABSTAINED = "abstained"


class FeatureFindingCode(StrEnum):
    UNIT_INVARIANT_FAILED = "unit_invariant_failed"
    TOPOLOGY_INVARIANT_FAILED = "topology_invariant_failed"
    PERTURBATION_INVARIANT_FAILED = "perturbation_invariant_failed"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class FeatureConstructorConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    units_reference: ArtifactReference
    locked: Literal[True] = True
    topology_invariants_required: Literal[True] = True
    perturbation_invariants_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1503_MAX_EVIDENCE)


class FeatureConstructorPolicy(FrozenModel):
    require_units: Literal[True] = True
    require_parent_binding: Literal[True] = True
    quarantine_unresolved: Literal[True] = True
    maximum_features: int = Field(ge=1, le=M1503_MAX_FEATURES)
    configuration: FeatureConstructorConfiguration


class MechanisticFeature(FrozenModel):
    feature_id: Identifier
    kind: FeatureKind
    label: NonEmptyStr
    value: NonEmptyStr
    numeric_value: float | None = None
    unit: NonEmptyStr
    parent_component: Literal["complex_activity"] = M1503_PARENT
    support_status: FeatureSupportStatus
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1503_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1503_MAX_EVIDENCE)

    @model_validator(mode="after")
    def supported_feature_has_evidence(self) -> MechanisticFeature:
        if self.support_status is FeatureSupportStatus.SUPPORTED and not self.evidence:
            raise ValueError("supported mechanistic feature requires evidence")
        return self


class MechanisticFeatureObject(FrozenModel):
    feature_object_id: Identifier
    version: SemanticVersion
    features: tuple[MechanisticFeature, ...] = Field(
        min_length=1, max_length=M1503_MAX_FEATURES
    )
    material_assumptions: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1503_MAX_ASSUMPTIONS
    )
    units_locked: Literal[True] = True
    topology_invariant_verified: Literal[True] = True
    perturbation_invariant_verified: Literal[True] = True
    locked_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1503_MAX_EVIDENCE)

    @model_validator(mode="after")
    def feature_ids_are_unique(self) -> MechanisticFeatureObject:
        ids = tuple(item.feature_id for item in self.features)
        if len(ids) != len(set(ids)):
            raise ValueError("mechanistic feature ids must be unique")
        return self


class FeatureFinding(FrozenModel):
    finding_id: Identifier
    code: FeatureFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1503_MAX_EVIDENCE)


class ConstructComplexActivityMechanisticFeaturesRequest(FrozenModel):
    """Provisional request for an interpretable mechanistic feature object."""

    operation: Literal["construct_complex_activity_mechanistic_features"] = M1503_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1503_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    longitudinal_recurrence_result: ArtifactReference
    policy: FeatureConstructorPolicy
    candidate_features: tuple[MechanisticFeature, ...] = Field(
        min_length=1, max_length=M1503_MAX_FEATURES
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1503_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_features_are_unique_and_bounded(
        self,
    ) -> ConstructComplexActivityMechanisticFeaturesRequest:
        if self.longitudinal_recurrence_result.media_type != M1503_M1502_RESULT_MEDIA_TYPE:
            raise ValueError("feature request must bind the provisional M15-02 result")
        ids = tuple(item.feature_id for item in self.candidate_features)
        if len(ids) != len(set(ids)):
            raise ValueError("request feature ids must be unique")
        if len(self.candidate_features) > self.policy.maximum_features:
            raise ValueError("request exceeds configured feature limit")
        return self


class ComplexActivityMechanisticFeatureResult(FrozenModel):
    """Mechanistic feature object with explicit invariants and safe failure."""

    output_type: Literal["complex_activity_mechanistic_features"] = (
        "complex_activity_mechanistic_features"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1503_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructComplexActivityMechanisticFeaturesRequest
    status: FeatureConstructorStatus
    feature_object: MechanisticFeatureObject | None = None
    findings: tuple[FeatureFinding, ...] = Field(default=(), max_length=M1503_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M1503_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1503_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityMechanisticFeatureResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is FeatureConstructorStatus.CONSTRUCTED:
            if (
                self.feature_object is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("constructed result requires a supported feature object")
        elif (
            self.feature_object is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no feature object and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1503_CONTRACT_VERSION",
    "M1503_GATE",
    "M1503_M1502_RESULT_MEDIA_TYPE",
    "M1503_MAX_ASSUMPTIONS",
    "M1503_MAX_CANONICAL_REQUEST_BYTES",
    "M1503_MAX_CANONICAL_RESULT_BYTES",
    "M1503_MAX_EVIDENCE",
    "M1503_MAX_FEATURES",
    "M1503_MAX_FINDINGS",
    "M1503_MODULE_ID",
    "M1503_OPERATION",
    "M1503_OUTPUT_MEDIA_TYPE",
    "M1503_OWNER",
    "M1503_PARENT",
    "M1503_PROVISIONAL_ABI",
    "M1503_SAFETY_CLASS",
    "ComplexActivityMechanisticFeatureResult",
    "ConstructComplexActivityMechanisticFeaturesRequest",
    "FeatureConstructorConfiguration",
    "FeatureConstructorPolicy",
    "FeatureConstructorStatus",
    "FeatureFinding",
    "FeatureFindingCode",
    "FeatureKind",
    "FeatureSupportStatus",
    "MechanisticFeature",
    "MechanisticFeatureObject",
]
