"""Provisional M18-04 intended-use adapter contracts.

M18-04 converts research output into a bounded intended-use object and policy
decision beneath Spatial proteomics projection. Evidence tier, claim ceiling,
audience, display semantics, uncertainty and unsupported claims are explicit;
this adapter never emits treatment recommendations. The public ABI is
provisional pending Quality engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m18_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M18-04 dossier slice.
M1804_MODULE_ID: Final = "GLIO-PROTEOGEN-M18-04"
M1804_OPERATION: Final = "adapt_biomarker_panel_intended_use"
M1804_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1804_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-04+json"
M1804_M1803_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-03+json"
M1804_PARENT: Final = "biomarker panel"
M1804_OWNER: Final = "Quality engineering"
M1804_SAFETY_CLASS: Final = "S2"
M1804_GATE: Final = "G3"
M1804_PROVISIONAL_ABI: Final = True
M1804_MAX_PROHIBITED_INTERPRETATIONS: Final = 64
M1804_MAX_DISPLAY_SECTIONS: Final = 32
M1804_MAX_EVIDENCE: Final = 64
M1804_MAX_FINDINGS: Final = 64
M1804_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1804_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1804_EVIDENCE_CLAIM: Final = (
    "Caller-declared M18-04 intended-use, evidence tier, claim ceiling and "
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
    ALLOWED = "allowed"
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
        min_length=1, max_length=M1804_MAX_PROHIBITED_INTERPRETATIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1804_MAX_EVIDENCE)

    @model_validator(mode="after")
    def prohibited_interpretations_are_unique(self) -> ClaimCeiling:
        if len(self.prohibited_interpretations) != len(set(self.prohibited_interpretations)):
            raise ValueError("prohibited interpretations must be unique")
        return self


class DisplaySemantics(FrozenModel):
    section_order: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1804_MAX_DISPLAY_SECTIONS
    )
    show_uncertainty: Literal[True] = True
    show_disagreements: Literal[True] = True
    safe_default: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1804_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1804_MAX_EVIDENCE)


class PolicyDecision(FrozenModel):
    status: PolicyDecisionStatus
    reason_code: AdapterFindingCode
    rationale: NonEmptyStr
    blocked_claims: tuple[NonEmptyStr, ...] = Field(
        default=(), max_length=M1804_MAX_PROHIBITED_INTERPRETATIONS
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1804_MAX_EVIDENCE)

    @model_validator(mode="after")
    def blocked_claims_match_status(self) -> PolicyDecision:
        if self.status is PolicyDecisionStatus.BLOCKED and not self.blocked_claims:
            raise ValueError("blocked policy decision requires blocked claims")
        if self.status is PolicyDecisionStatus.ALLOWED and self.blocked_claims:
            raise ValueError("allowed policy decision cannot carry blocked claims")
        return self


class IntendedUseSpecificObject(FrozenModel):
    """Bounded presentation object derived from one upstream result."""

    object_id: Identifier
    version: SemanticVersion
    parent_target: Literal["biomarker panel"] = M1804_PARENT
    upstream_result: ArtifactReference
    registration: IntendedUseRegistration
    policy_decision: PolicyDecision
    uncertainty: UncertaintyProfile
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1804_MAX_EVIDENCE)


class AdapterFinding(FrozenModel):
    finding_id: Identifier
    code: AdapterFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1804_MAX_EVIDENCE)


class AdaptBiomarkerPanelIntendedUseRequest(FrozenModel):
    """Provisional request bound to the M18-03 integrated evidence result."""

    operation: Literal["adapt_biomarker_panel_intended_use"] = M1804_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1804_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    registration: IntendedUseRegistration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1804_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AdaptBiomarkerPanelIntendedUseRequest:
        if self.upstream_result.media_type != M1804_M1803_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M18-03 integrated evidence")
        digests = tuple(item.digest for item in self.source_artifacts)
        if len(digests) != len(set(digests)):
            raise ValueError("request source artifact digests must be unique")
        return self


class BiomarkerPanelIntendedUseAdapterResult(FrozenModel):
    """Intended-use-specific object and policy decision with safe abstention."""

    output_type: Literal["biomarker_panel_intended_use_adapter_result"] = (
        "biomarker_panel_intended_use_adapter_result"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1804_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdaptBiomarkerPanelIntendedUseRequest
    status: AdapterStatus
    adapted_object: IntendedUseSpecificObject | None = None
    policy_decision: PolicyDecision
    findings: tuple[AdapterFinding, ...] = Field(default=(), max_length=M1804_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M1804_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1804_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelIntendedUseAdapterResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != f"result.{self.request_digest.removeprefix('sha256:')}":
            raise ValueError("result identifier must be derived from request digest")
        if self.status is AdapterStatus.ADAPTED:
            if (
                self.adapted_object is None
                or self.abstention_reason is not None
                or self.policy_decision.status
                not in {PolicyDecisionStatus.ALLOWED, PolicyDecisionStatus.REVIEW_REQUIRED}
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
            ):
                raise ValueError("adapted result requires review-only bounded policy output")
        elif (
            self.adapted_object is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no adapted object and safe status")
        if self.status is AdapterStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstained result requires human review")
        if self.adapted_object is not None and (
            self.adapted_object.upstream_result != self.request.upstream_result
            or self.adapted_object.registration != self.request.registration
        ):
            raise ValueError("adapted object must bind request registration and upstream")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1804_CONTRACT_VERSION",
    "M1804_EVIDENCE_CLAIM",
    "M1804_GATE",
    "M1804_M1803_INPUT_MEDIA_TYPE",
    "M1804_MAX_CANONICAL_REQUEST_BYTES",
    "M1804_MAX_CANONICAL_RESULT_BYTES",
    "M1804_MAX_DISPLAY_SECTIONS",
    "M1804_MAX_EVIDENCE",
    "M1804_MAX_FINDINGS",
    "M1804_MAX_PROHIBITED_INTERPRETATIONS",
    "M1804_MODULE_ID",
    "M1804_OPERATION",
    "M1804_OUTPUT_MEDIA_TYPE",
    "M1804_OWNER",
    "M1804_PARENT",
    "M1804_PROVISIONAL_ABI",
    "M1804_SAFETY_CLASS",
    "AdaptBiomarkerPanelIntendedUseRequest",
    "AdapterFinding",
    "AdapterFindingCode",
    "AdapterStatus",
    "BiomarkerPanelIntendedUseAdapterResult",
    "ClaimCeiling",
    "DisplaySemantics",
    "IntendedUseKind",
    "IntendedUseRegistration",
    "IntendedUseSpecificObject",
    "PolicyDecision",
    "PolicyDecisionStatus",
]
