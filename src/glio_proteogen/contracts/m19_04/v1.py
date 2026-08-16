"""Provisional M19-04 intended-use adapter contracts.

M19-04 converts research output into a bounded intended-use object and policy
decision beneath Immunopeptidomic evidence. Evidence tier, claim ceiling,
audience, display semantics, uncertainty and unsupported claims are explicit;
this adapter never emits treatment recommendations. The public ABI is
provisional pending Clinical science owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m19_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M19-04 dossier slice.
M1904_MODULE_ID: Final = "GLIO-PROTEOGEN-M19-04"
M1904_OPERATION: Final = "adapt_proteotype_intended_use"
M1904_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1904_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-04+json"
M1904_M1903_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-03+json"
M1904_PARENT: Final = "proteotype"
M1904_OWNER: Final = "Clinical science"
M1904_SAFETY_CLASS: Final = "S2"
M1904_GATE: Final = "G3"
M1904_PROVISIONAL_ABI: Final = True
M1904_MAX_PROHIBITED_INTERPRETATIONS: Final = 64
M1904_MAX_DISPLAY_SECTIONS: Final = 32
M1904_MAX_EVIDENCE: Final = 64
M1904_MAX_FINDINGS: Final = 64
M1904_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1904_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1904_EVIDENCE_CLAIM: Final = (
    "Caller-declared M19-04 intended-use, evidence tier, claim ceiling and "
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
        min_length=1, max_length=M1904_MAX_PROHIBITED_INTERPRETATIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1904_MAX_EVIDENCE)


class DisplaySemantics(FrozenModel):
    section_order: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1904_MAX_DISPLAY_SECTIONS
    )
    show_uncertainty: Literal[True] = True
    show_disagreements: Literal[True] = True
    safe_default: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1904_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1904_MAX_EVIDENCE)


class PolicyDecision(FrozenModel):
    status: PolicyDecisionStatus
    reason_code: AdapterFindingCode
    rationale: NonEmptyStr
    blocked_claims: tuple[NonEmptyStr, ...] = Field(
        default=(), max_length=M1904_MAX_PROHIBITED_INTERPRETATIONS
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1904_MAX_EVIDENCE)


class IntendedUseSpecificObject(FrozenModel):
    """Bounded presentation object derived from one upstream result."""

    object_id: Identifier
    version: SemanticVersion
    parent_target: Literal["proteotype"] = M1904_PARENT
    upstream_result: ArtifactReference
    registration: IntendedUseRegistration
    policy_decision: PolicyDecision
    uncertainty: UncertaintyProfile
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1904_MAX_EVIDENCE)


class AdapterFinding(FrozenModel):
    finding_id: Identifier
    code: AdapterFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1904_MAX_EVIDENCE)


class AdaptProteotypeIntendedUseRequest(FrozenModel):
    """Provisional request bound to the M19-03 integrated evidence result."""

    operation: Literal["adapt_proteotype_intended_use"] = M1904_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1904_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    registration: IntendedUseRegistration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1904_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdaptProteotypeIntendedUseRequest:
        if self.upstream_result.media_type != M1904_M1903_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M19-03 integrated evidence")
        return self


class ProteotypeIntendedUseAdapterResult(FrozenModel):
    """Intended-use-specific object and policy decision with safe abstention."""

    output_type: Literal["proteotype_intended_use_adapter_result"] = (
        "proteotype_intended_use_adapter_result"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1904_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdaptProteotypeIntendedUseRequest
    status: AdapterStatus
    adapted_object: IntendedUseSpecificObject | None = None
    policy_decision: PolicyDecision
    findings: tuple[AdapterFinding, ...] = Field(default=(), max_length=M1904_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1904_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1904_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeIntendedUseAdapterResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is AdapterStatus.ADAPTED:
            if (
                self.adapted_object is None
                or self.abstention_reason is not None
                or self.policy_decision.status
                not in {PolicyDecisionStatus.ALLOWED, PolicyDecisionStatus.REVIEW_REQUIRED}
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("adapted result requires supported bounded policy output")
        elif (
            self.adapted_object is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no adapted object and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1904_CONTRACT_VERSION",
    "M1904_EVIDENCE_CLAIM",
    "M1904_GATE",
    "M1904_M1903_INPUT_MEDIA_TYPE",
    "M1904_MAX_CANONICAL_REQUEST_BYTES",
    "M1904_MAX_CANONICAL_RESULT_BYTES",
    "M1904_MAX_DISPLAY_SECTIONS",
    "M1904_MAX_EVIDENCE",
    "M1904_MAX_FINDINGS",
    "M1904_MAX_PROHIBITED_INTERPRETATIONS",
    "M1904_MODULE_ID",
    "M1904_OPERATION",
    "M1904_OUTPUT_MEDIA_TYPE",
    "M1904_OWNER",
    "M1904_PARENT",
    "M1904_PROVISIONAL_ABI",
    "M1904_SAFETY_CLASS",
    "AdaptProteotypeIntendedUseRequest",
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
    "ProteotypeIntendedUseAdapterResult",
]
