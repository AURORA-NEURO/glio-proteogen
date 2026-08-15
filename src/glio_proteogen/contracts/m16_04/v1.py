"""Provisional M16-04 intended-use adapter contracts.

The dossier requires conversion of research output into a bounded context of
use, audience, evidence tier, claim ceiling, and display semantics.  The ABI is
not frozen; this contract emits only a registered intended-use object and typed
policy decision for the protein-RNA discordance parent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m16_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 5568-5611.
M1604_MODULE_ID: Final = "GLIO-PROTEOGEN-M16-04"
M1604_OPERATION: Final = "adapt_protein_rna_discordance_intended_use"
M1604_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1604_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-04+json"
M1604_M1601_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-01+json"
M1604_PARENT: Final = "protein_rna_discordance"
M1604_OWNER: Final = "Bioinformatics"
M1604_SAFETY_CLASS: Final = "S2"
M1604_GATE: Final = "G3"
M1604_PROVISIONAL_ABI: Final = True
M1604_MAX_CLAIMS: Final = 64
M1604_MAX_BLOCKED_CLAIMS: Final = 64
M1604_MAX_EVIDENCE: Final = 64
M1604_MAX_REASONS: Final = 64
M1604_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1604_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class IntendedUseContext(StrEnum):
    RESEARCH_DISCOVERY = "research_discovery"
    METHODS_DEVELOPMENT = "methods_development"
    SCIENTIFIC_VALIDATION = "scientific_validation"
    CLINICAL_REVIEW = "clinical_review"


class IntendedUseAudience(StrEnum):
    RESEARCHER = "researcher"
    SCIENTIFIC_REVIEWER = "scientific_reviewer"
    CLINICAL_REVIEWER = "clinical_reviewer"
    QUALITY_REVIEWER = "quality_reviewer"


class EvidenceTier(StrEnum):
    EXPLORATORY = "exploratory"
    VALIDATED = "validated"
    REVIEW_READY = "review_ready"


class ClaimCeiling(StrEnum):
    DESCRIPTIVE = "descriptive"
    MECHANISTIC_HYPOTHESIS = "mechanistic_hypothesis"
    SUPPORTED_MECHANISM = "supported_mechanism"
    ABSTAIN = "abstain"


class DisplaySemantic(StrEnum):
    VISIBLE = "visible"
    QUALIFIED = "qualified"
    REVIEW_ONLY = "review_only"
    HIDDEN = "hidden"


class PolicyDecisionStatus(StrEnum):
    ALLOWED = "allowed"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"
    ABSTAINED = "abstained"


class AdapterStatus(StrEnum):
    ADAPTED = "adapted"
    ABSTAINED = "abstained"


class IntendedUseFindingCode(StrEnum):
    UNREGISTERED_INTENDED_USE = "unregistered_intended_use"
    CLAIM_CEILING_EXCEEDED = "claim_ceiling_exceeded"
    EVIDENCE_TIER_INSUFFICIENT = "evidence_tier_insufficient"
    DISPLAY_RESTRICTED = "display_restricted"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class AdapterConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    registered_policy_required: Literal[True] = True
    claim_ceiling_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1604_MAX_EVIDENCE)


class IntendedUsePolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    context: IntendedUseContext
    audience: IntendedUseAudience
    minimum_evidence_tier: EvidenceTier
    maximum_claim_ceiling: ClaimCeiling
    display_semantic: DisplaySemantic
    permitted_claims: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1604_MAX_CLAIMS)
    prohibited_claims: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1604_MAX_BLOCKED_CLAIMS
    )
    registered: Literal[True] = True
    configuration: AdapterConfiguration

    @model_validator(mode="after")
    def policy_is_closed(self) -> IntendedUsePolicy:
        permitted = set(self.permitted_claims)
        prohibited = set(self.prohibited_claims)
        if len(permitted) != len(self.permitted_claims):
            raise ValueError("permitted claims must be unique")
        if len(prohibited) != len(self.prohibited_claims):
            raise ValueError("prohibited claims must be unique")
        if permitted & prohibited:
            raise ValueError("permitted and prohibited claims must be disjoint")
        if self.context is IntendedUseContext.CLINICAL_REVIEW:
            if self.audience is not IntendedUseAudience.CLINICAL_REVIEWER:
                raise ValueError("clinical review requires a clinical reviewer audience")
            if self.minimum_evidence_tier is EvidenceTier.EXPLORATORY:
                raise ValueError("clinical review cannot accept exploratory evidence")
        if (
            self.maximum_claim_ceiling is ClaimCeiling.SUPPORTED_MECHANISM
            and self.minimum_evidence_tier is EvidenceTier.EXPLORATORY
        ):
            raise ValueError("supported mechanism claims require non-exploratory evidence")
        if (
            self.display_semantic is DisplaySemantic.HIDDEN
            and self.maximum_claim_ceiling is not ClaimCeiling.ABSTAIN
        ):
            raise ValueError("hidden display requires an abstaining claim ceiling")
        return self


class PolicyDecision(FrozenModel):
    decision_id: Identifier
    status: PolicyDecisionStatus
    policy_id: Identifier
    reasons: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1604_MAX_REASONS)
    registered_intended_use: Literal[True] = True
    auditable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1604_MAX_EVIDENCE)

    @model_validator(mode="after")
    def decision_status_is_safe(self) -> PolicyDecision:
        if self.status is PolicyDecisionStatus.ALLOWED and not self.evidence:
            raise ValueError("allowed policy decisions require evidence")
        if (
            self.status in {PolicyDecisionStatus.BLOCKED, PolicyDecisionStatus.ABSTAINED}
            and not self.reasons
        ):
            raise ValueError("blocked or abstained decisions require reasons")
        return self


class IntendedUseObject(FrozenModel):
    object_id: Identifier
    version: SemanticVersion
    upstream_artifact: ArtifactReference
    context: IntendedUseContext
    audience: IntendedUseAudience
    evidence_tier: EvidenceTier
    claim_ceiling: ClaimCeiling
    display_semantic: DisplaySemantic
    permitted_claims: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1604_MAX_CLAIMS)
    blocked_claims: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1604_MAX_BLOCKED_CLAIMS
    )
    policy_decision: PolicyDecision
    material_assumptions: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1604_MAX_REASONS
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1604_MAX_EVIDENCE)

    @model_validator(mode="after")
    def object_matches_policy(self) -> IntendedUseObject:
        if self.policy_decision.policy_id == "":
            raise ValueError("intended-use object requires a policy binding")
        if (
            self.claim_ceiling is ClaimCeiling.ABSTAIN
            and self.policy_decision.status is PolicyDecisionStatus.ALLOWED
        ):
            raise ValueError("abstaining claim ceiling cannot be allowed")
        if len(set(self.permitted_claims)) != len(self.permitted_claims):
            raise ValueError("object permitted claims must be unique")
        if len(set(self.blocked_claims)) != len(self.blocked_claims):
            raise ValueError("object blocked claims must be unique")
        if set(self.permitted_claims) & set(self.blocked_claims):
            raise ValueError("object permitted and blocked claims must be disjoint")
        return self


class IntendedUseFinding(FrozenModel):
    finding_id: Identifier
    code: IntendedUseFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1604_MAX_EVIDENCE)


class AdaptProteinRnaDiscordanceIntendedUseRequest(FrozenModel):
    """Provisional request for bounded intended-use adaptation."""

    operation: Literal["adapt_protein_rna_discordance_intended_use"] = M1604_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1604_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_resolution_result: ArtifactReference
    policy: IntendedUsePolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1604_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_binds_upstream_result(self) -> AdaptProteinRnaDiscordanceIntendedUseRequest:
        if self.upstream_resolution_result.media_type != M1604_M1601_RESULT_MEDIA_TYPE:
            raise ValueError("intended-use request must bind the provisional M16-01 result")
        return self


class ProteinRnaDiscordanceIntendedUseResult(FrozenModel):
    """Intended-use-specific object and policy decision with safe abstention."""

    output_type: Literal["protein_rna_discordance_intended_use"] = (
        "protein_rna_discordance_intended_use"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1604_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AdaptProteinRnaDiscordanceIntendedUseRequest
    status: AdapterStatus
    intended_use_object: IntendedUseObject | None = None
    policy_decision: PolicyDecision
    findings: tuple[IntendedUseFinding, ...] = Field(default=(), max_length=M1604_MAX_REASONS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1604_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1604_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceIntendedUseResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is AdapterStatus.ADAPTED:
            if (
                self.intended_use_object is None
                or self.policy_decision.status is PolicyDecisionStatus.BLOCKED
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("adapted result requires a supported unblocked object")
            if not self.evidence or self.human_review_required:
                raise ValueError("adapted result requires evidence and no mandatory review")
        elif (
            self.intended_use_object is not None
            or self.abstention_reason is None
            or self.policy_decision.status is PolicyDecisionStatus.ALLOWED
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no object and safe status")
        if self.status is AdapterStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstained result requires human review")
        if len({finding.finding_id for finding in self.findings}) != len(self.findings):
            raise ValueError("findings must have unique identifiers")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1604_CONTRACT_VERSION",
    "M1604_GATE",
    "M1604_M1601_RESULT_MEDIA_TYPE",
    "M1604_MAX_BLOCKED_CLAIMS",
    "M1604_MAX_CANONICAL_REQUEST_BYTES",
    "M1604_MAX_CANONICAL_RESULT_BYTES",
    "M1604_MAX_CLAIMS",
    "M1604_MAX_EVIDENCE",
    "M1604_MAX_REASONS",
    "M1604_MODULE_ID",
    "M1604_OPERATION",
    "M1604_OUTPUT_MEDIA_TYPE",
    "M1604_OWNER",
    "M1604_PARENT",
    "M1604_PROVISIONAL_ABI",
    "M1604_SAFETY_CLASS",
    "AdaptProteinRnaDiscordanceIntendedUseRequest",
    "AdapterConfiguration",
    "AdapterStatus",
    "ClaimCeiling",
    "DisplaySemantic",
    "EvidenceTier",
    "IntendedUseAudience",
    "IntendedUseContext",
    "IntendedUseFinding",
    "IntendedUseFindingCode",
    "IntendedUseObject",
    "IntendedUsePolicy",
    "PolicyDecision",
    "PolicyDecisionStatus",
    "ProteinRnaDiscordanceIntendedUseResult",
]
