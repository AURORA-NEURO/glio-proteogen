"""Provisional M11-02 context and subtype-stratifier contracts.

The dossier requires typed biological context, applicable mechanisms, support
boundaries, and safe abstention, but does not freeze the public ABI, context
catalogue, or stratification rules.  All symbols remain provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m11_02.canonical import (
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

M1102_MODULE_ID: Final = "GLIO-PROTEOGEN-M11-02"
M1102_OPERATION: Final = "stratify_variant_peptide_context"
M1102_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1102_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-02+json"
M1102_HYPOTHESIS_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-01+json"
M1102_PARENT: Final = "variant_peptide"
M1102_OWNER: Final = "ML engineering"
M1102_SAFETY_CLASS: Final = "S2"
M1102_GATE: Final = "G1"
M1102_PROVISIONAL_ABI: Final = True
M1102_MAX_OBSERVATIONS: Final = 128
M1102_MAX_MECHANISMS: Final = 256
M1102_MAX_RULES: Final = 128
M1102_MAX_EVIDENCE: Final = 64
M1102_MAX_DIAGNOSTICS: Final = 128
M1102_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1102_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1102_EVIDENCE_CLAIM: Final = (
    "Caller-declared context and mechanism-applicability evidence; issuer authority "
    "is not authenticated."
)


class ContextDimension(StrEnum):
    DISEASE_CLASS = "disease_class"
    SUBTYPE = "subtype"
    AGE = "age"
    TERRITORY = "territory"
    TREATMENT_ERA = "treatment_era"
    SPECIMEN = "specimen"
    PLATFORM = "platform"
    BIOLOGICAL_CONTEXT = "biological_context"


class MechanismApplicabilityStatus(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class ContextStratificationStatus(StrEnum):
    STRATIFIED = "stratified"
    ABSTAINED = "abstained"


class ContextObservation(FrozenModel):
    dimension: ContextDimension
    value: NonEmptyStr
    source_artifact: ArtifactReference
    support_score: float = Field(ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1102_MAX_EVIDENCE)


class ContextStratificationRule(FrozenModel):
    rule_id: Identifier
    dimension: ContextDimension
    criterion: NonEmptyStr
    allowed_values: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1102_MAX_OBSERVATIONS
    )
    prohibited_proxies: tuple[NonEmptyStr, ...] = Field(default=(), max_length=32)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1102_MAX_EVIDENCE)


class ContextStratificationPolicy(FrozenModel):
    """Locked dimensions, rules, and support boundary for context mapping."""

    policy_id: Identifier
    version: SemanticVersion
    dimensions: tuple[ContextDimension, ...] = Field(
        min_length=1, max_length=len(ContextDimension)
    )
    rules: tuple[ContextStratificationRule, ...] = Field(
        min_length=1, max_length=M1102_MAX_RULES
    )
    minimum_support_score: float = Field(ge=0.0, le=1.0)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1102_MAX_EVIDENCE)

    @model_validator(mode="after")
    def policy_is_closed(self) -> ContextStratificationPolicy:
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("context dimensions must be unique")
        rule_ids = tuple(item.rule_id for item in self.rules)
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("context stratification rule ids must be unique")
        if any(item.dimension not in self.dimensions for item in self.rules):
            raise ValueError("context rule dimension must be declared by policy")
        return self


class MechanismApplicability(FrozenModel):
    mechanism_id: Identifier
    status: MechanismApplicabilityStatus
    rationale: NonEmptyStr
    context_dimensions: tuple[ContextDimension, ...] = Field(
        min_length=1, max_length=len(ContextDimension)
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1102_MAX_EVIDENCE)


class ContextProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    observations: tuple[ContextObservation, ...] = Field(
        min_length=1, max_length=M1102_MAX_OBSERVATIONS
    )
    applicable_mechanisms: tuple[MechanismApplicability, ...] = Field(
        min_length=1, max_length=M1102_MAX_MECHANISMS
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1102_MAX_EVIDENCE)

    @model_validator(mode="after")
    def observations_are_unique(self) -> ContextProfile:
        dimensions = tuple(item.dimension for item in self.observations)
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("context observations must contain each dimension once")
        mechanism_ids = tuple(item.mechanism_id for item in self.applicable_mechanisms)
        if len(mechanism_ids) != len(set(mechanism_ids)):
            raise ValueError("mechanism applicability ids must be unique")
        return self


class ContextStratifierDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: MechanismApplicabilityStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1102_MAX_EVIDENCE)


class StratifyVariantPeptideContextRequest(FrozenModel):
    """Provisional request bound to the M11-01 hypothesis registry result."""

    operation: Literal["stratify_variant_peptide_context"] = M1102_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1102_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    hypothesis_registry: ArtifactReference
    policy: ContextStratificationPolicy
    observations: tuple[ContextObservation, ...] = Field(
        min_length=1, max_length=M1102_MAX_OBSERVATIONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1102_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> StratifyVariantPeptideContextRequest:
        if self.hypothesis_registry.media_type != M1102_HYPOTHESIS_MEDIA_TYPE:
            raise ValueError("context request must bind the provisional M11-01 registry")
        dimensions = tuple(item.dimension for item in self.observations)
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("request observations must contain each dimension once")
        if any(item.dimension not in self.policy.dimensions for item in self.observations):
            raise ValueError("request observation dimension is outside policy scope")
        return self


class VariantPeptideContextStratificationResult(FrozenModel):
    """Typed context profile and applicable mechanisms with safe status."""

    output_type: Literal["variant_peptide_context_profile"] = "variant_peptide_context_profile"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1102_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: StratifyVariantPeptideContextRequest
    status: ContextStratificationStatus
    profile: ContextProfile | None = None
    diagnostics: tuple[ContextStratifierDiagnostic, ...] = Field(
        default=(), max_length=M1102_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant_peptide"] = M1102_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1102_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideContextStratificationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is ContextStratificationStatus.STRATIFIED:
            if (
                self.profile is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("stratified result requires supported context profile")
        elif (
            self.profile is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no profile and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1102_CONTRACT_VERSION",
    "M1102_EVIDENCE_CLAIM",
    "M1102_GATE",
    "M1102_HYPOTHESIS_MEDIA_TYPE",
    "M1102_MAX_CANONICAL_REQUEST_BYTES",
    "M1102_MAX_CANONICAL_RESULT_BYTES",
    "M1102_MAX_DIAGNOSTICS",
    "M1102_MAX_EVIDENCE",
    "M1102_MAX_MECHANISMS",
    "M1102_MAX_OBSERVATIONS",
    "M1102_MAX_RULES",
    "M1102_MODULE_ID",
    "M1102_OPERATION",
    "M1102_OUTPUT_MEDIA_TYPE",
    "M1102_OWNER",
    "M1102_PARENT",
    "M1102_PROVISIONAL_ABI",
    "M1102_SAFETY_CLASS",
    "ContextDimension",
    "ContextObservation",
    "ContextProfile",
    "ContextStratificationPolicy",
    "ContextStratificationRule",
    "ContextStratificationStatus",
    "ContextStratifierDiagnostic",
    "MechanismApplicability",
    "MechanismApplicabilityStatus",
    "StratifyVariantPeptideContextRequest",
    "VariantPeptideContextStratificationResult",
]
