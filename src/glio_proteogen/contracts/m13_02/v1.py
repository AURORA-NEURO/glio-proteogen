"""Provisional M13-02 context and subtype stratifier contracts.

The dossier defines a typed context profile and applicable mechanism set under
the Variant-peptide channel.  Its public ABI is not frozen; these types retain
conflict, support, provenance, and safe-abstention boundaries explicitly.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m13_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 4400-4443.
M1302_MODULE_ID: Final = "GLIO-PROTEOGEN-M13-02"
M1302_OPERATION: Final = "stratify_proteotype_context"
M1302_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1302_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m13-02+json"
M1302_PARENT: Final = "proteotype"
M1302_OWNER: Final = "Clinical science"
M1302_SAFETY_CLASS: Final = "S2"
M1302_GATE: Final = "G1"
M1302_PROVISIONAL_ABI: Final = True
M1302_MAX_OBSERVATIONS: Final = 128
M1302_MAX_MECHANISMS: Final = 256
M1302_MAX_EVIDENCE: Final = 64
M1302_MAX_FINDINGS: Final = 64
M1302_MAX_DIMENSIONS: Final = 8
M1302_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1302_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1302_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1302_MAX_EVIDENCE)


class StratifierPolicy(FrozenModel):
    required_dimensions: tuple[ContextDimension, ...] = Field(
        min_length=1, max_length=M1302_MAX_DIMENSIONS
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1302_MAX_EVIDENCE)

    @model_validator(mode="after")
    def applicable_mechanism_has_evidence(self) -> ApplicableMechanism:
        if self.applicability is MechanismApplicability.APPLICABLE and not self.evidence:
            raise ValueError("applicable mechanism requires evidence")
        return self


class ContextFinding(FrozenModel):
    finding_id: Identifier
    code: ContextFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1302_MAX_EVIDENCE)


class ProteotypeContextProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    observations: tuple[ContextObservation, ...] = Field(
        min_length=1, max_length=M1302_MAX_OBSERVATIONS
    )
    unresolved_dimensions: tuple[ContextDimension, ...] = Field(
        default=(), max_length=M1302_MAX_DIMENSIONS
    )
    locked: Literal[True] = True
    conflict_preserved: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1302_MAX_EVIDENCE)

    @model_validator(mode="after")
    def observation_ids_are_unique(self) -> ProteotypeContextProfile:
        ids = tuple(item.observation_id for item in self.observations)
        if len(ids) != len(set(ids)):
            raise ValueError("context observation ids must be unique")
        if len(set(self.unresolved_dimensions)) != len(self.unresolved_dimensions):
            raise ValueError("unresolved context dimensions must be unique")
        return self


class StratifyProteotypeContextRequest(FrozenModel):
    """Provisional request for a proteotype context and mechanism set."""

    operation: Literal["stratify_proteotype_context"] = M1302_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1302_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    variant_peptide_result: ArtifactReference
    policy: StratifierPolicy
    observations: tuple[ContextObservation, ...] = Field(
        min_length=1, max_length=M1302_MAX_OBSERVATIONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1302_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_observations_are_unique(self) -> StratifyProteotypeContextRequest:
        ids = tuple(item.observation_id for item in self.observations)
        if len(ids) != len(set(ids)):
            raise ValueError("request context observation ids must be unique")
        return self


class ProteotypeContextStratificationResult(FrozenModel):
    """Typed proteotype context and mechanisms with explicit safe failure."""

    output_type: Literal["proteotype_context_stratification"] = (
        "proteotype_context_stratification"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1302_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: StratifyProteotypeContextRequest
    status: ContextStratificationStatus
    context_profile: ProteotypeContextProfile | None = None
    applicable_mechanisms: tuple[ApplicableMechanism, ...] = Field(
        default=(), max_length=M1302_MAX_MECHANISMS
    )
    findings: tuple[ContextFinding, ...] = Field(default=(), max_length=M1302_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1302_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1302_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeContextStratificationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is ContextStratificationStatus.STRATIFIED:
            if (
                self.context_profile is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("stratified result requires a supported context profile")
        elif (
            self.context_profile is not None
            or self.applicable_mechanisms
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no profile and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1302_CONTRACT_VERSION",
    "M1302_GATE",
    "M1302_MAX_CANONICAL_REQUEST_BYTES",
    "M1302_MAX_CANONICAL_RESULT_BYTES",
    "M1302_MAX_DIMENSIONS",
    "M1302_MAX_EVIDENCE",
    "M1302_MAX_FINDINGS",
    "M1302_MAX_MECHANISMS",
    "M1302_MAX_OBSERVATIONS",
    "M1302_MODULE_ID",
    "M1302_OPERATION",
    "M1302_OUTPUT_MEDIA_TYPE",
    "M1302_OWNER",
    "M1302_PARENT",
    "M1302_PROVISIONAL_ABI",
    "M1302_SAFETY_CLASS",
    "ApplicableMechanism",
    "ContextDimension",
    "ContextFinding",
    "ContextFindingCode",
    "ContextObservation",
    "ContextObservationStatus",
    "ContextStratificationStatus",
    "MechanismApplicability",
    "ProteotypeContextProfile",
    "ProteotypeContextStratificationResult",
    "StratifierConfiguration",
    "StratifierPolicy",
    "StratifyProteotypeContextRequest",
]
