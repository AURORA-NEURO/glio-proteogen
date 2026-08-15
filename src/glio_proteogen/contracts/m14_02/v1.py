"""Provisional M14-02 context and subtype stratifier contracts.

The dossier places this module beneath Microenvironment protein deconvolution
and makes it responsible for a typed context profile and applicable mechanism
set for the protein-subtype parent.  The ABI is not frozen; disagreement,
support, provenance, and safe abstention remain explicit.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m14_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 4760-4803.
M1402_MODULE_ID: Final = "GLIO-PROTEOGEN-M14-02"
M1402_OPERATION: Final = "stratify_protein_subtype_context"
M1402_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1402_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-02+json"
M1402_PARENT: Final = "protein_subtype"
M1402_OWNER: Final = "Data engineering"
M1402_SAFETY_CLASS: Final = "S2"
M1402_GATE: Final = "G1"
M1402_PROVISIONAL_ABI: Final = True
M1402_MAX_OBSERVATIONS: Final = 128
M1402_MAX_MECHANISMS: Final = 256
M1402_MAX_EVIDENCE: Final = 64
M1402_MAX_FINDINGS: Final = 64
M1402_MAX_DIMENSIONS: Final = 8
M1402_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1402_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class ContextDimension(StrEnum):
    DISEASE_CLASS = "disease_class"
    SUBTYPE = "subtype"
    AGE = "age"
    TERRITORY = "territory"
    TREATMENT_ERA = "treatment_era"
    SPECIMEN = "specimen"
    PLATFORM = "platform"
    BIOLOGICAL_CONTEXT = "biological_context"


class ContextObservationStatus(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    CONFLICTED = "conflicted"
    UNRESOLVED = "unresolved"
    ABSTAINED = "abstained"


class MechanismApplicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_SUPPORTED = "not_supported"
    UNKNOWN = "unknown"
    ABSTAINED = "abstained"


class ContextStratificationStatus(StrEnum):
    STRATIFIED = "stratified"
    ABSTAINED = "abstained"


class ContextFindingCode(StrEnum):
    IDENTITY_UNRESOLVED = "identity_unresolved"
    CONSENT_UNRESOLVED = "consent_unresolved"
    CONTEXT_CONFLICT = "context_conflict"
    UNSUPPORTED_PROXY_BLOCKED = "unsupported_proxy_blocked"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class ContextObservation(FrozenModel):
    """One typed observation; conflicting values remain represented."""

    observation_id: Identifier
    dimension: ContextDimension
    value: NonEmptyStr
    normalized_value: NonEmptyStr | None = None
    status: ContextObservationStatus
    source_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1402_MAX_EVIDENCE)

    @model_validator(mode="after")
    def supported_observation_has_evidence(self) -> ContextObservation:
        if self.status is ContextObservationStatus.SUPPORTED and not self.evidence:
            raise ValueError("supported context observation requires evidence")
        if self.status is ContextObservationStatus.UNRESOLVED and self.normalized_value is not None:
            raise ValueError("unresolved context observation cannot carry normalized value")
        return self


class StratifierConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    identity_and_consent_gated: Literal[True] = True
    conflict_preserving: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1402_MAX_EVIDENCE)


class StratifierPolicy(FrozenModel):
    required_dimensions: tuple[ContextDimension, ...] = Field(
        min_length=1, max_length=M1402_MAX_DIMENSIONS
    )
    quarantine_unresolved: Literal[True] = True
    prohibit_all_omics_fusion: Literal[True] = True
    configuration: StratifierConfiguration

    @model_validator(mode="after")
    def required_dimensions_are_unique(self) -> StratifierPolicy:
        if len(set(self.required_dimensions)) != len(self.required_dimensions):
            raise ValueError("required context dimensions must be unique")
        return self


class ApplicableMechanism(FrozenModel):
    mechanism_id: Identifier
    label: NonEmptyStr
    applicability: MechanismApplicability
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1402_MAX_EVIDENCE)

    @model_validator(mode="after")
    def applicable_mechanism_has_evidence(self) -> ApplicableMechanism:
        if self.applicability is MechanismApplicability.APPLICABLE and not self.evidence:
            raise ValueError("applicable mechanism requires evidence")
        return self


class ContextFinding(FrozenModel):
    finding_id: Identifier
    code: ContextFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1402_MAX_EVIDENCE)


class ProteinSubtypeContextProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    observations: tuple[ContextObservation, ...] = Field(
        min_length=1, max_length=M1402_MAX_OBSERVATIONS
    )
    unresolved_dimensions: tuple[ContextDimension, ...] = Field(
        default=(), max_length=M1402_MAX_DIMENSIONS
    )
    locked: Literal[True] = True
    conflict_preserved: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1402_MAX_EVIDENCE)

    @model_validator(mode="after")
    def observation_ids_are_unique(self) -> ProteinSubtypeContextProfile:
        ids = tuple(item.observation_id for item in self.observations)
        if len(ids) != len(set(ids)):
            raise ValueError("context observation ids must be unique")
        if len(set(self.unresolved_dimensions)) != len(self.unresolved_dimensions):
            raise ValueError("unresolved context dimensions must be unique")
        return self


class StratifyProteinSubtypeContextRequest(FrozenModel):
    """Provisional request for a protein subtype context and mechanism set."""

    operation: Literal["stratify_protein_subtype_context"] = M1402_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1402_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    microenvironment_deconvolution_result: ArtifactReference
    policy: StratifierPolicy
    observations: tuple[ContextObservation, ...] = Field(
        min_length=1, max_length=M1402_MAX_OBSERVATIONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1402_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_observations_are_unique(self) -> StratifyProteinSubtypeContextRequest:
        ids = tuple(item.observation_id for item in self.observations)
        if len(ids) != len(set(ids)):
            raise ValueError("request context observation ids must be unique")
        return self


class ProteinSubtypeContextStratificationResult(FrozenModel):
    """Typed protein subtype context and mechanisms with safe failure."""

    output_type: Literal["protein_subtype_context_stratification"] = (
        "protein_subtype_context_stratification"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1402_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: StratifyProteinSubtypeContextRequest
    status: ContextStratificationStatus
    context_profile: ProteinSubtypeContextProfile | None = None
    applicable_mechanisms: tuple[ApplicableMechanism, ...] = Field(
        default=(), max_length=M1402_MAX_MECHANISMS
    )
    findings: tuple[ContextFinding, ...] = Field(default=(), max_length=M1402_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M1402_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1402_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeContextStratificationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        mechanism_ids = tuple(item.mechanism_id for item in self.applicable_mechanisms)
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(mechanism_ids) != len(set(mechanism_ids)):
            raise ValueError("applicable mechanism ids must be unique")
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("context finding ids must be unique")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("every result requires evidence references with the evidence role")
        if self.status is ContextStratificationStatus.STRATIFIED:
            if (
                self.context_profile is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.human_review_required
            ):
                raise ValueError("stratified result requires a supported context profile")
        elif (
            self.context_profile is not None
            or self.applicable_mechanisms
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no profile and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Expose all seven uncertainty dimensions for context stratification."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "Declared context observations passed the provisional support domain."
            if supported
            else "Context support, conflict, or required controls were not safely evaluable."
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
            "Age, territory, treatment era, specimen, platform, subtype, disease class, and "
            "biological context sensitivity remain explicit.",
        ),
    )


def expected_provenance(
    request: StratifyProteinSubtypeContextRequest, request_digest: Sha256Digest
) -> ProvenanceRecord:
    """Bind input digests and seven caller-declared control decisions."""

    references = request.context.references
    controls = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1402_MODULE_ID,
        module_version=M1402_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.microenvironment_deconvolution_result.digest,
            *(item.digest for item in request.source_artifacts),
        ),
        configuration_digest=request.policy.configuration.model_reference.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


__all__ = [
    "M1402_CONTRACT_VERSION",
    "M1402_GATE",
    "M1402_MAX_CANONICAL_REQUEST_BYTES",
    "M1402_MAX_CANONICAL_RESULT_BYTES",
    "M1402_MAX_DIMENSIONS",
    "M1402_MAX_EVIDENCE",
    "M1402_MAX_FINDINGS",
    "M1402_MAX_MECHANISMS",
    "M1402_MAX_OBSERVATIONS",
    "M1402_MODULE_ID",
    "M1402_OPERATION",
    "M1402_OUTPUT_MEDIA_TYPE",
    "M1402_OWNER",
    "M1402_PARENT",
    "M1402_PROVISIONAL_ABI",
    "M1402_SAFETY_CLASS",
    "ApplicableMechanism",
    "ContextDimension",
    "ContextFinding",
    "ContextFindingCode",
    "ContextObservation",
    "ContextObservationStatus",
    "ContextStratificationStatus",
    "MechanismApplicability",
    "ProteinSubtypeContextProfile",
    "ProteinSubtypeContextStratificationResult",
    "StratifierConfiguration",
    "StratifierPolicy",
    "StratifyProteinSubtypeContextRequest",
    "expected_provenance",
    "expected_uncertainty",
]
