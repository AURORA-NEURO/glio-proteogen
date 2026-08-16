"""Provisional M13-08 mechanism evidence dossier contracts.

The M13-08 dossier requires a review-ready, reconstructable chain from input
through mechanism, counter-evidence, validation route, uncertainty and claim
ceiling.  It does not freeze the public ABI, dossier vocabulary, operation,
media type, or capacities.  All symbols here are provisional scaffolding
pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m13_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M13-08 dossier slice.
M1308_MODULE_ID: Final = "GLIO-PROTEOGEN-M13-08"
M1308_OPERATION: Final = "assemble_proteotype_mechanism_dossier"
M1308_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1308_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m13-08+json"
M1308_M1307_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m13-07+json"
M1308_PARENT: Final = "proteotype"
M1308_OWNER: Final = "ML engineering"
M1308_SAFETY_CLASS: Final = "S2"
M1308_GATE: Final = "G3"
M1308_PROVISIONAL_ABI: Final = True
M1308_MAX_LINKS: Final = 512
M1308_MAX_COUNTER_EVIDENCE: Final = 256
M1308_MAX_VALIDATION_ROUTES: Final = 128
M1308_MAX_PROHIBITED_INTERPRETATIONS: Final = 64
M1308_MAX_EVIDENCE: Final = 64
M1308_MAX_DIAGNOSTICS: Final = 128
M1308_MAX_FINDINGS: Final = 64
M1308_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1308_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1308_EVIDENCE_CLAIM: Final = (
    "Caller-declared M13-08 mechanism evidence dossier material; issuer authority "
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
    predecessor_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1308_MAX_LINKS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1308_MAX_EVIDENCE)
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=64)


class CounterEvidenceRecord(FrozenModel):
    counter_evidence_id: Identifier
    statement: NonEmptyStr
    impact: NonEmptyStr
    challenges_link_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1308_MAX_LINKS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1308_MAX_EVIDENCE)


class ValidationRoute(FrozenModel):
    route_id: Identifier
    method: NonEmptyStr
    status: ValidationRouteStatus
    required_experiment: NonEmptyStr
    acceptance_criterion: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1308_MAX_EVIDENCE)


class ClaimCeiling(FrozenModel):
    maximum_claim: NonEmptyStr
    prohibited_interpretations: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1308_MAX_PROHIBITED_INTERPRETATIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1308_MAX_EVIDENCE)


class MechanismDossierConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: NonEmptyStr
    source_manifest: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1308_MAX_EVIDENCE
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1308_MAX_EVIDENCE)


class MechanismEvidenceDossier(FrozenModel):
    """Review-ready dossier with complete chain, challenge and claim ceiling."""

    dossier_id: Identifier
    version: SemanticVersion
    links: tuple[MechanismEvidenceLink, ...] = Field(min_length=1, max_length=M1308_MAX_LINKS)
    counter_evidence: tuple[CounterEvidenceRecord, ...] = Field(
        min_length=1, max_length=M1308_MAX_COUNTER_EVIDENCE
    )
    validation_routes: tuple[ValidationRoute, ...] = Field(
        min_length=1, max_length=M1308_MAX_VALIDATION_ROUTES
    )
    uncertainty: UncertaintyProfile
    claim_ceiling: ClaimCeiling
    configuration: MechanismDossierConfiguration
    reviewer_id: Identifier
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1308_MAX_EVIDENCE)

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
        known_roots = {"source", "upstream"} | {
            item.artifact_id for item in self.configuration.source_manifest
        }
        for counter in self.counter_evidence:
            if not set(counter.challenges_link_ids) <= known_links:
                raise ValueError("counter-evidence references an unknown link")
        for link in self.links:
            if not set(link.predecessor_ids) <= known_links | set(counter_ids) | known_roots:
                raise ValueError("mechanism link references an unknown predecessor")
        if not any(item.kind is MechanismEvidenceLinkKind.INPUT for item in self.links):
            raise ValueError("dossier requires an input link")
        if not any(item.kind is MechanismEvidenceLinkKind.CLAIM_CEILING for item in self.links):
            raise ValueError("dossier requires a claim-ceiling link")
        if not any(
            item.status is ValidationRouteStatus.COMPLETE for item in self.validation_routes
        ):
            raise ValueError("dossier requires a complete validation route")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("dossier requires evidence references with the evidence role")
        return self


class MechanismDossierDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: DossierDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1308_MAX_EVIDENCE)


class AssembleProteotypeMechanismDossierRequest(FrozenModel):
    """Provisional request ABI bound to the M13-07 upstream adjudication."""

    operation: Literal["assemble_proteotype_mechanism_dossier"] = M1308_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1308_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: MechanismDossierConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1308_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AssembleProteotypeMechanismDossierRequest:
        if self.upstream_result.media_type != M1308_M1307_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M13-07 adjudication result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("source artifact references must be unique")
        return self


class ProteotypeMechanismDossierResult(FrozenModel):
    """Review-ready mechanism dossier with explicit claim ceiling and abstention."""

    output_type: Literal["proteotype_mechanism_evidence_dossier"] = (
        "proteotype_mechanism_evidence_dossier"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1308_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AssembleProteotypeMechanismDossierRequest
    status: MechanismDossierStatus
    dossier: MechanismEvidenceDossier | None = None
    diagnostics: tuple[MechanismDossierDiagnostic, ...] = Field(
        min_length=1, max_length=M1308_MAX_DIAGNOSTICS
    )
    findings: tuple[MechanismDossierFindingCode, ...] = Field(
        default=(), max_length=M1308_MAX_FINDINGS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1308_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1308_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeMechanismDossierResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("diagnostic ids must be unique")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("every result requires evidence references with the evidence role")
        failed = {DossierDiagnosticStatus.FAIL, DossierDiagnosticStatus.NOT_EVALUABLE}
        if self.status is MechanismDossierStatus.READY:
            if (
                self.dossier is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed for item in self.diagnostics)
                or self.human_review_required
            ):
                raise ValueError("ready result requires supported, reconstructable dossier")
        elif (
            self.dossier is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no dossier and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Construct all seven uncertainty dimensions without hiding abstention."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "The closed dossier chain, counter-evidence, validation route, and claim ceiling "
            "are present in the provisional support domain."
            if supported
            else "The mechanism dossier chain or validation support was not safely evaluable."
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
            "Weak links, counter-evidence, validation requirements, and claim ceiling remain "
            "visible.",
            "The provisional probability is metadata only and is not a population coverage claim.",
        ),
    )


def expected_provenance(
    request: AssembleProteotypeMechanismDossierRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project seven caller-declared controls into auditable provenance."""

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
        module_id=M1308_MODULE_ID,
        module_version=M1308_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(artifact.digest for artifact in request.configuration.source_manifest),
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
    "M1308_CONTRACT_VERSION",
    "M1308_EVIDENCE_CLAIM",
    "M1308_GATE",
    "M1308_M1307_INPUT_MEDIA_TYPE",
    "M1308_MAX_CANONICAL_REQUEST_BYTES",
    "M1308_MAX_CANONICAL_RESULT_BYTES",
    "M1308_MAX_COUNTER_EVIDENCE",
    "M1308_MAX_DIAGNOSTICS",
    "M1308_MAX_EVIDENCE",
    "M1308_MAX_FINDINGS",
    "M1308_MAX_LINKS",
    "M1308_MAX_PROHIBITED_INTERPRETATIONS",
    "M1308_MAX_VALIDATION_ROUTES",
    "M1308_MODULE_ID",
    "M1308_OPERATION",
    "M1308_OUTPUT_MEDIA_TYPE",
    "M1308_OWNER",
    "M1308_PARENT",
    "M1308_PROVISIONAL_ABI",
    "M1308_SAFETY_CLASS",
    "AssembleProteotypeMechanismDossierRequest",
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
    "ProteotypeMechanismDossierResult",
    "ValidationRoute",
    "ValidationRouteStatus",
    "expected_provenance",
    "expected_uncertainty",
]
