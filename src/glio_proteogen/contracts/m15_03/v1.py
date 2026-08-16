"""Provisional M15-03 mechanistic feature constructor contracts.

The dossier requires interpretable pathway, topology, state, lineage, kinetics,
spatial, or regulatory features tied to the complex-activity parent.  The ABI is
not frozen; this contract retains units, topology/perturbation invariants,
source evidence, uncertainty, and safe abstention.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from glio_proteogen.contracts.m15_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
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
    UncertaintyEstimate,
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

    @field_validator("numeric_value")
    @classmethod
    def numeric_value_is_finite(cls, value: float | None) -> float | None:
        _require_finite_value(value)
        return value

    @model_validator(mode="after")
    def supported_feature_has_evidence(self) -> MechanisticFeature:
        if self.support_status is FeatureSupportStatus.SUPPORTED and not self.evidence:
            raise ValueError("supported mechanistic feature requires evidence")
        _require_feature_unit(self)
        return self


def _require_feature_unit(feature: MechanisticFeature) -> None:
    if feature.numeric_value is not None and not feature.unit:
        raise ValueError("numeric mechanistic feature requires a unit")


def _require_finite_value(value: float | None) -> None:
    if value is not None and not isfinite(value):
        raise ValueError("numeric mechanistic feature value must be finite")


class MechanisticFeatureObject(FrozenModel):
    feature_object_id: Identifier
    version: SemanticVersion
    features: tuple[MechanisticFeature, ...] = Field(min_length=1, max_length=M1503_MAX_FEATURES)
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
        _require_feature_parent(self.features)
        return self


def _require_feature_parent(features: tuple[MechanisticFeature, ...]) -> None:
    if any(item.parent_component != M1503_PARENT for item in features):
        raise ValueError("mechanistic features must bind the complex_activity parent")


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
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("result evidence must contain evidence-role references")
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
        if self.status is FeatureConstructorStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstention requires human review acknowledgement")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Expose every uncertainty dimension and preserve abstention semantics."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "Units, topology, perturbation invariants, parent binding, and source evidence "
            "are reconstructable within the declared support domain."
            if supported
            else "One or more feature inputs, invariants, controls, or upstream quality "
            "conditions were not safely evaluable."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Topology and perturbation sensitivity remain explicit and require external "
            "validation.",
            "Unsupported or missing evidence is never converted into a negative feature.",
        ),
    )


def expected_provenance(
    request: ConstructComplexActivityMechanisticFeaturesRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project the seven caller-declared controls into auditable provenance."""

    refs = request.context.references
    decisions = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1503_MODULE_ID,
        module_version=M1503_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.longitudinal_recurrence_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(item.evidence_digest for item in decisions),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


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
    "expected_provenance",
    "expected_uncertainty",
]
