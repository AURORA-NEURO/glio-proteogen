"""Provisional M12-08 mechanism evidence dossier contracts.

The M12-08 dossier requires a review-ready, reconstructable chain from input
through mechanism, counter-evidence, validation route, uncertainty and claim
ceiling.  It does not freeze the public ABI, dossier vocabulary, operation,
media type, or capacities.  All symbols here are provisional scaffolding
pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m12_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M12-08 dossier slice.
M1208_MODULE_ID: Final = "GLIO-PROTEOGEN-M12-08"
M1208_OPERATION: Final = "assemble_biomarker_panel_mechanism_dossier"
M1208_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1208_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-08+json"
M1208_M1207_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-07+json"
M1208_PARENT: Final = "biomarker_panel"
M1208_OWNER: Final = "Bioinformatics"
M1208_SAFETY_CLASS: Final = "S2"
M1208_GATE: Final = "G3"
M1208_PROVISIONAL_ABI: Final = True
M1208_MAX_LINKS: Final = 512
M1208_MAX_COUNTER_EVIDENCE: Final = 256
M1208_MAX_VALIDATION_ROUTES: Final = 128
M1208_MAX_PROHIBITED_INTERPRETATIONS: Final = 64
M1208_MAX_EVIDENCE: Final = 64
M1208_MAX_DIAGNOSTICS: Final = 128
M1208_MAX_FINDINGS: Final = 64
M1208_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1208_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1208_EVIDENCE_CLAIM: Final = (
    "Caller-declared M12-08 mechanism evidence dossier material; issuer authority "
    "is not authenticated."
)


class MechanismEvidenceLinkKind(StrEnum):
    INPUT = "input"
    MECHANISM = "mechanism"
    COUNTER_EVIDENCE = "counter_evidence"
    VALIDATION = "validation"
    UNCERTAINTY = "uncertainty"
    CLAIM_CEILING = "claim_ceiling"


class ValidationRouteStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class MechanismDossierStatus(StrEnum):
    READY = "ready"
    ABSTAINED = "abstained"


class DossierDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class MechanismDossierFindingCode(StrEnum):
    CHAIN_INCOMPLETE = "chain_incomplete"
    COUNTER_EVIDENCE_MISSING = "counter_evidence_missing"
    VALIDATION_ROUTE_UNRESOLVED = "validation_route_unresolved"
    CLAIM_CEILING_MISSING = "claim_ceiling_missing"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class MechanismEvidenceLink(FrozenModel):
    """One reconstructable link in the mechanism evidence chain."""

    link_id: Identifier
    kind: MechanismEvidenceLinkKind
    assertion: NonEmptyStr
    predecessor_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1208_MAX_LINKS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1208_MAX_EVIDENCE)
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=64)


class CounterEvidenceRecord(FrozenModel):
    counter_evidence_id: Identifier
    statement: NonEmptyStr
    impact: NonEmptyStr
    challenges_link_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1208_MAX_LINKS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1208_MAX_EVIDENCE)


class ValidationRoute(FrozenModel):
    route_id: Identifier
    method: NonEmptyStr
    status: ValidationRouteStatus
    required_experiment: NonEmptyStr
    acceptance_criterion: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1208_MAX_EVIDENCE)


class ClaimCeiling(FrozenModel):
    maximum_claim: NonEmptyStr
    prohibited_interpretations: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1208_MAX_PROHIBITED_INTERPRETATIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1208_MAX_EVIDENCE)


class MechanismDossierConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: NonEmptyStr
    source_manifest: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1208_MAX_EVIDENCE
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1208_MAX_EVIDENCE)


class MechanismEvidenceDossier(FrozenModel):
    """Review-ready dossier with complete chain, challenge and claim ceiling."""

    dossier_id: Identifier
    version: SemanticVersion
    links: tuple[MechanismEvidenceLink, ...] = Field(min_length=1, max_length=M1208_MAX_LINKS)
    counter_evidence: tuple[CounterEvidenceRecord, ...] = Field(
        min_length=1, max_length=M1208_MAX_COUNTER_EVIDENCE
    )
    validation_routes: tuple[ValidationRoute, ...] = Field(
        min_length=1, max_length=M1208_MAX_VALIDATION_ROUTES
    )
    uncertainty: UncertaintyProfile
    claim_ceiling: ClaimCeiling
    configuration: MechanismDossierConfiguration
    reviewer_id: Identifier
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1208_MAX_EVIDENCE)

    @model_validator(mode="after")
    def dossier_is_closed(self) -> MechanismEvidenceDossier:
        link_ids = tuple(item.link_id for item in self.links)
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("mechanism evidence link ids must be unique")
        counter_ids = tuple(item.counter_evidence_id for item in self.counter_evidence)
        if len(counter_ids) != len(set(counter_ids)):
            raise ValueError("counter-evidence ids must be unique")
        route_ids = tuple(item.route_id for item in self.validation_routes)
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("validation route ids must be unique")
        known_links = set(link_ids)
        for counter in self.counter_evidence:
            if not set(counter.challenges_link_ids) <= known_links:
                raise ValueError("counter-evidence references an unknown link")
        for link in self.links:
            if not set(link.predecessor_ids) <= known_links | set(counter_ids):
                raise ValueError("mechanism link references an unknown predecessor")
        return self


class MechanismDossierDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: DossierDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1208_MAX_EVIDENCE)


class AssembleBiomarkerPanelMechanismDossierRequest(FrozenModel):
    """Provisional request ABI bound to the M12-07 upstream adjudication."""

    operation: Literal["assemble_biomarker_panel_mechanism_dossier"] = M1208_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1208_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: MechanismDossierConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1208_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AssembleBiomarkerPanelMechanismDossierRequest:
        if self.upstream_result.media_type != M1208_M1207_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M12-07 adjudication result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("source artifact references must be unique")
        return self


class BiomarkerPanelMechanismDossierResult(FrozenModel):
    """Review-ready mechanism dossier with explicit claim ceiling and abstention."""

    output_type: Literal["biomarker_panel_mechanism_evidence_dossier"] = (
        "biomarker_panel_mechanism_evidence_dossier"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1208_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AssembleBiomarkerPanelMechanismDossierRequest
    status: MechanismDossierStatus
    dossier: MechanismEvidenceDossier | None = None
    diagnostics: tuple[MechanismDossierDiagnostic, ...] = Field(
        min_length=1, max_length=M1208_MAX_DIAGNOSTICS
    )
    findings: tuple[MechanismDossierFindingCode, ...] = Field(
        default=(), max_length=M1208_MAX_FINDINGS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker_panel"] = M1208_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1208_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelMechanismDossierResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        failed = {DossierDiagnosticStatus.FAIL, DossierDiagnosticStatus.NOT_EVALUABLE}
        if self.status is MechanismDossierStatus.READY:
            if (
                self.dossier is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed for item in self.diagnostics)
            ):
                raise ValueError("ready result requires supported, reconstructable dossier")
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
    "M1208_CONTRACT_VERSION",
    "M1208_EVIDENCE_CLAIM",
    "M1208_GATE",
    "M1208_M1207_INPUT_MEDIA_TYPE",
    "M1208_MAX_CANONICAL_REQUEST_BYTES",
    "M1208_MAX_CANONICAL_RESULT_BYTES",
    "M1208_MAX_COUNTER_EVIDENCE",
    "M1208_MAX_DIAGNOSTICS",
    "M1208_MAX_EVIDENCE",
    "M1208_MAX_FINDINGS",
    "M1208_MAX_LINKS",
    "M1208_MAX_PROHIBITED_INTERPRETATIONS",
    "M1208_MAX_VALIDATION_ROUTES",
    "M1208_MODULE_ID",
    "M1208_OPERATION",
    "M1208_OUTPUT_MEDIA_TYPE",
    "M1208_OWNER",
    "M1208_PARENT",
    "M1208_PROVISIONAL_ABI",
    "M1208_SAFETY_CLASS",
    "AssembleBiomarkerPanelMechanismDossierRequest",
    "BiomarkerPanelMechanismDossierResult",
    "ClaimCeiling",
    "CounterEvidenceRecord",
    "DossierDiagnosticStatus",
    "MechanismDossierConfiguration",
    "MechanismDossierDiagnostic",
    "MechanismDossierFindingCode",
    "MechanismDossierStatus",
    "MechanismEvidenceDossier",
    "MechanismEvidenceLink",
    "MechanismEvidenceLinkKind",
    "ValidationRoute",
    "ValidationRouteStatus",
]
