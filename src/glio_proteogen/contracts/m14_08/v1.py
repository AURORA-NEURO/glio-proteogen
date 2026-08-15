"""Provisional M14-08 mechanism evidence dossier contracts.

The dossier requires a review-ready, reconstructable chain from inputs through
mechanism, counter-evidence, validation route, uncertainty, and claim ceiling.
The ABI is not frozen; this contract makes those links and safe abstention
explicit for the protein-subtype parent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m14_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 5024-5067.
M1408_MODULE_ID: Final = "GLIO-PROTEOGEN-M14-08"
M1408_OPERATION: Final = "publish_protein_subtype_mechanism_dossier"
M1408_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1408_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-08+json"
M1408_PARENT: Final = "protein_subtype"
M1408_OWNER: Final = "Quality engineering"
M1408_SAFETY_CLASS: Final = "S2"
M1408_GATE: Final = "G3"
M1408_PROVISIONAL_ABI: Final = True
M1408_MAX_LINKS: Final = 256
M1408_MAX_CLAIMS: Final = 64
M1408_MAX_VALIDATION_ROUTES: Final = 64
M1408_MAX_EVIDENCE: Final = 64
M1408_MAX_FINDINGS: Final = 64
M1408_MAX_ASSUMPTIONS: Final = 64
M1408_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1408_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class EvidenceLinkKind(StrEnum):
    INPUT = "input"
    MECHANISM = "mechanism"
    COUNTER_EVIDENCE = "counter_evidence"
    VALIDATION = "validation"
    UNCERTAINTY = "uncertainty"
    CLAIM_CEILING = "claim_ceiling"


class EvidenceDisposition(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    CONFLICTED = "conflicted"
    UNRESOLVED = "unresolved"
    ABSTAINED = "abstained"


class ValidationRouteKind(StrEnum):
    ORTHOGONAL_ASSAY = "orthogonal_assay"
    PERTURBATION = "perturbation"
    REPLICATION = "replication"
    NEGATIVE_CONTROL = "negative_control"
    EXPERT_REVIEW = "expert_review"


class ValidationRouteStatus(StrEnum):
    COMPLETE = "complete"
    REQUIRED = "required"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class ClaimLevel(StrEnum):
    OBSERVATIONAL = "observational"
    MECHANISTIC_HYPOTHESIS = "mechanistic_hypothesis"
    SUPPORTED_MECHANISM = "supported_mechanism"


class DossierStatus(StrEnum):
    REVIEW_READY = "review_ready"
    ABSTAINED = "abstained"


class DossierFindingCode(StrEnum):
    BROKEN_EVIDENCE_CHAIN = "broken_evidence_chain"
    COUNTER_EVIDENCE_REQUIRED = "counter_evidence_required"
    VALIDATION_ROUTE_REQUIRED = "validation_route_required"
    CLAIM_CEILING_REACHED = "claim_ceiling_reached"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class DossierConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    counter_evidence_required: Literal[True] = True
    reviewer_reconstruction_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1408_MAX_EVIDENCE)


class EvidenceLink(FrozenModel):
    link_id: Identifier
    kind: EvidenceLinkKind
    source_artifact: ArtifactReference
    target_id: Identifier
    claim: NonEmptyStr
    disposition: EvidenceDisposition
    counter_evidence: tuple[EvidenceReference, ...] = Field(
        default=(), max_length=M1408_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1408_MAX_EVIDENCE)

    @model_validator(mode="after")
    def supported_link_has_evidence(self) -> EvidenceLink:
        if self.disposition is EvidenceDisposition.SUPPORTED and not self.evidence:
            raise ValueError("supported evidence link requires evidence")
        return self


class ValidationRoute(FrozenModel):
    route_id: Identifier
    kind: ValidationRouteKind
    objective: NonEmptyStr
    next_experiment: NonEmptyStr
    status: ValidationRouteStatus
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1408_MAX_EVIDENCE)


class MechanismClaim(FrozenModel):
    claim_id: Identifier
    mechanism_id: Identifier
    statement: NonEmptyStr
    level: ClaimLevel
    claim_ceiling: NonEmptyStr
    required_link_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1408_MAX_LINKS)
    counter_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1408_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1408_MAX_EVIDENCE)


class DossierFinding(FrozenModel):
    finding_id: Identifier
    code: DossierFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1408_MAX_EVIDENCE)


class MechanismEvidenceDossier(FrozenModel):
    dossier_id: Identifier
    version: SemanticVersion
    links: tuple[EvidenceLink, ...] = Field(min_length=2, max_length=M1408_MAX_LINKS)
    claims: tuple[MechanismClaim, ...] = Field(min_length=1, max_length=M1408_MAX_CLAIMS)
    validation_routes: tuple[ValidationRoute, ...] = Field(
        min_length=1, max_length=M1408_MAX_VALIDATION_ROUTES
    )
    material_assumptions: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1408_MAX_ASSUMPTIONS
    )
    claim_ceiling: NonEmptyStr
    reviewer_reconstructable: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1408_MAX_EVIDENCE)

    @model_validator(mode="after")
    def dossier_links_are_closed(self) -> MechanismEvidenceDossier:
        link_ids = tuple(item.link_id for item in self.links)
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("dossier link ids must be unique")
        route_ids = tuple(item.route_id for item in self.validation_routes)
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("validation route ids must be unique")
        link_set = set(link_ids)
        for claim in self.claims:
            if not set(claim.required_link_ids).issubset(link_set):
                raise ValueError("claim references an unavailable evidence link")
        return self


class PublishProteinSubtypeMechanismDossierRequest(FrozenModel):
    """Provisional request for a review-ready mechanism evidence dossier."""

    operation: Literal["publish_protein_subtype_mechanism_dossier"] = M1408_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1408_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_mechanism_result: ArtifactReference
    configuration: DossierConfiguration
    dossier: MechanismEvidenceDossier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1408_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None


class ProteinSubtypeMechanismEvidenceDossierResult(FrozenModel):
    """Review-ready mechanism dossier with explicit claim ceiling and abstention."""

    output_type: Literal["protein_subtype_mechanism_evidence_dossier"] = (
        "protein_subtype_mechanism_evidence_dossier"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1408_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishProteinSubtypeMechanismDossierRequest
    status: DossierStatus
    dossier: MechanismEvidenceDossier | None = None
    findings: tuple[DossierFinding, ...] = Field(default=(), max_length=M1408_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M1408_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1408_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeMechanismEvidenceDossierResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is DossierStatus.REVIEW_READY:
            if (
                self.dossier is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("review-ready result requires a supported dossier")
        elif (
            self.dossier is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no dossier and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1408_CONTRACT_VERSION",
    "M1408_GATE",
    "M1408_MAX_ASSUMPTIONS",
    "M1408_MAX_CANONICAL_REQUEST_BYTES",
    "M1408_MAX_CANONICAL_RESULT_BYTES",
    "M1408_MAX_CLAIMS",
    "M1408_MAX_EVIDENCE",
    "M1408_MAX_FINDINGS",
    "M1408_MAX_LINKS",
    "M1408_MAX_VALIDATION_ROUTES",
    "M1408_MODULE_ID",
    "M1408_OPERATION",
    "M1408_OUTPUT_MEDIA_TYPE",
    "M1408_OWNER",
    "M1408_PARENT",
    "M1408_PROVISIONAL_ABI",
    "M1408_SAFETY_CLASS",
    "ClaimLevel",
    "DossierConfiguration",
    "DossierFinding",
    "DossierFindingCode",
    "DossierStatus",
    "EvidenceDisposition",
    "EvidenceLink",
    "EvidenceLinkKind",
    "MechanismClaim",
    "MechanismEvidenceDossier",
    "ProteinSubtypeMechanismEvidenceDossierResult",
    "PublishProteinSubtypeMechanismDossierRequest",
    "ValidationRoute",
    "ValidationRouteKind",
    "ValidationRouteStatus",
]
