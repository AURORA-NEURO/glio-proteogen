"""Provisional M20-04 intended-use adapter contracts.

M20-04 converts research output into a bounded intended-use object and policy
decision beneath Biomarker-panel translation. Evidence tier, claim ceiling,
audience, display semantics, uncertainty and unsupported claims are explicit;
this adapter never emits treatment recommendations. The public ABI is
provisional pending Data engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m20_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M20-04 dossier slice.
M2004_MODULE_ID: Final = "GLIO-PROTEOGEN-M20-04"
M2004_OPERATION: Final = "adapt_protein_subtype_intended_use"
M2004_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2004_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-04+json"
M2004_M2003_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-03+json"
M2004_PARENT: Final = "protein subtype"
M2004_OWNER: Final = "Data engineering"
M2004_SAFETY_CLASS: Final = "S2"
M2004_GATE: Final = "G3"
M2004_PROVISIONAL_ABI: Final = True
M2004_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2004_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7008-7048"
M2004_MAX_PROHIBITED_INTERPRETATIONS: Final = 64
M2004_MAX_DISPLAY_SECTIONS: Final = 32
M2004_MAX_EVIDENCE: Final = 64
M2004_MAX_FINDINGS: Final = 64
M2004_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2004_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2004_EVIDENCE_CLAIM: Final = (
    "Caller-declared M20-04 intended-use, evidence tier, claim ceiling and "
    "display-policy material; issuer authority is not authenticated."
)


class IntendedUseKind(StrEnum):
    RESEARCH = "research"
    INTERNAL_VALIDATION = "internal_validation"
    CLINICAL_REVIEW = "clinical_review"
    RELEASE_REVIEW = "release_review"


class PolicyDecisionStatus(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"
    ABSTAINED = "abstained"


class AdapterStatus(StrEnum):
    ADAPTED = "adapted"
    ABSTAINED = "abstained"


class AdapterFindingCode(StrEnum):
    CLAIM_EXCEEDS_CEILING = "claim_exceeds_ceiling"
    EVIDENCE_TIER_MISSING = "evidence_tier_missing"
    INTENDED_USE_UNREGISTERED = "intended_use_unregistered"
    AUDIENCE_UNSUPPORTED = "audience_unsupported"
    DISPLAY_SEMANTICS_INCOMPLETE = "display_semantics_incomplete"
    TREATMENT_RECOMMENDATION_BLOCKED = "treatment_recommendation_blocked"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class ClaimCeiling(FrozenModel):
    maximum_claim: NonEmptyStr
    prohibited_interpretations: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M2004_MAX_PROHIBITED_INTERPRETATIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def prohibited_interpretations_are_unique(self) -> ClaimCeiling:
        if len(self.prohibited_interpretations) != len(set(self.prohibited_interpretations)):
            raise ValueError("prohibited interpretations must be unique")
        return self


class DisplaySemantics(FrozenModel):
    section_order: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M2004_MAX_DISPLAY_SECTIONS
    )
    show_uncertainty: Literal[True] = True
    show_disagreements: Literal[True] = True
    safe_default: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def section_order_is_unique(self) -> DisplaySemantics:
        if len(self.section_order) != len(set(self.section_order)):
            raise ValueError("display section order must be unique")
        return self


class IntendedUseRegistration(FrozenModel):
    registration_id: Identifier
    version: SemanticVersion
    intended_use: IntendedUseKind
    audience: NonEmptyStr
    evidence_tier: int = Field(ge=1, le=4)
    claim_ceiling: ClaimCeiling
    display_semantics: DisplaySemantics
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def registration_is_closed(self) -> IntendedUseRegistration:
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("intended-use registration evidence must be unique")
        return self


class PolicyDecision(FrozenModel):
    status: PolicyDecisionStatus
    reason_code: AdapterFindingCode
    rationale: NonEmptyStr
    blocked_claims: tuple[NonEmptyStr, ...] = Field(
        default=(), max_length=M2004_MAX_PROHIBITED_INTERPRETATIONS
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def blocked_claims_are_unique(self) -> PolicyDecision:
        if len(self.blocked_claims) != len(set(self.blocked_claims)):
            raise ValueError("blocked claims must be unique")
        return self


class IntendedUseSpecificObject(FrozenModel):
    """Bounded presentation object derived from one upstream result."""

    object_id: Identifier
    version: SemanticVersion
    parent_target: Literal["protein subtype"] = M2004_PARENT
    upstream_result: ArtifactReference
    registration: IntendedUseRegistration
    policy_decision: PolicyDecision
    uncertainty: UncertaintyProfile
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2004_MAX_EVIDENCE)


class AdapterFinding(FrozenModel):
    finding_id: Identifier
    code: AdapterFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2004_MAX_EVIDENCE)


class AdaptProteinSubtypeIntendedUseRequest(FrozenModel):
    """Provisional request bound to the M20-03 integrated evidence result."""

    operation: Literal["adapt_protein_subtype_intended_use"] = M2004_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2004_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    registration: IntendedUseRegistration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2004_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdaptProteinSubtypeIntendedUseRequest:
        if self.upstream_result.media_type != M2004_M2003_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M20-03 integrated evidence")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("intended-use source artifact ids must be unique")
        return self


class ProteinSubtypeIntendedUseAdapterResult(FrozenModel):
    """Intended-use-specific object and policy decision with safe abstention."""

    output_type: Literal["protein_subtype_intended_use_adapter_result"] = (
        "protein_subtype_intended_use_adapter_result"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2004_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdaptProteinSubtypeIntendedUseRequest
    status: AdapterStatus
    adapted_object: IntendedUseSpecificObject | None = None
    policy_decision: PolicyDecision
    findings: tuple[AdapterFinding, ...] = Field(default=(), max_length=M2004_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2004_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2004_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeIntendedUseAdapterResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("adapter finding ids must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("adapter result evidence digests must be unique")
        if self.status is AdapterStatus.ADAPTED:
            if (
                self.adapted_object is None
                or self.abstention_reason is not None
                or self.policy_decision.status
                not in {PolicyDecisionStatus.ALLOWED, PolicyDecisionStatus.REVIEW_REQUIRED}
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
            ):
                raise ValueError("adapted result requires review-only bounded policy output")
        elif (
            self.adapted_object is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no adapted object, safe status, and review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2004_CONTRACT_VERSION",
    "M2004_DOSSIER_SHA256",
    "M2004_DOSSIER_SLICE",
    "M2004_EVIDENCE_CLAIM",
    "M2004_GATE",
    "M2004_M2003_INPUT_MEDIA_TYPE",
    "M2004_MAX_CANONICAL_REQUEST_BYTES",
    "M2004_MAX_CANONICAL_RESULT_BYTES",
    "M2004_MAX_DISPLAY_SECTIONS",
    "M2004_MAX_EVIDENCE",
    "M2004_MAX_FINDINGS",
    "M2004_MAX_PROHIBITED_INTERPRETATIONS",
    "M2004_MODULE_ID",
    "M2004_OPERATION",
    "M2004_OUTPUT_MEDIA_TYPE",
    "M2004_OWNER",
    "M2004_PARENT",
    "M2004_PROVISIONAL_ABI",
    "M2004_SAFETY_CLASS",
    "AdaptProteinSubtypeIntendedUseRequest",
    "AdapterFinding",
    "AdapterFindingCode",
    "AdapterStatus",
    "ClaimCeiling",
    "DisplaySemantics",
    "IntendedUseKind",
    "IntendedUseRegistration",
    "IntendedUseSpecificObject",
    "PolicyDecision",
    "PolicyDecisionStatus",
    "ProteinSubtypeIntendedUseAdapterResult",
]
