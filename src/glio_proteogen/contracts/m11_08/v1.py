"""Provisional M11-08 mechanism evidence dossier contracts.

M11-08 owns a review-ready, reconstructable mechanism-evidence chain beneath
the variant-peptide parent. The ABI is intentionally provisional: the dossier
describes behavior and safety boundaries, but does not freeze public names,
media types, endpoints, or a production model. The contract records every
caller-declared reference without dereferencing external payloads and makes
abstention structurally distinct from a dossier.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m11_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
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

# PROVISIONAL ABI: inferred solely from the M11-08 dossier slice.
M1108_MODULE_ID: Final = "GLIO-PROTEOGEN-M11-08"
M1108_OPERATION: Final = "assemble_variant_peptide_mechanism_dossier"
M1108_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1108_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-08+json"
M1108_M1107_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-07+json"
M1108_PARENT: Final = "variant_peptide"
M1108_OWNER: Final = "Computational biology"
M1108_SAFETY_CLASS: Final = "S2"
M1108_GATE: Final = "G3"
M1108_PROVISIONAL_ABI: Final = True
M1108_MAX_SOURCES: Final = 64
M1108_MAX_LINKS: Final = 512
M1108_MAX_COUNTER_EVIDENCE: Final = 256
M1108_MAX_VALIDATION_ROUTES: Final = 128
M1108_MAX_PROHIBITED_INTERPRETATIONS: Final = 64
M1108_MAX_ASSUMPTIONS: Final = 128
M1108_MAX_RECONSTRUCTION_STEPS: Final = 256
M1108_MAX_EVIDENCE: Final = 64
M1108_MAX_DIAGNOSTICS: Final = 128
M1108_MAX_FINDINGS: Final = 64
M1108_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1108_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1108_EVIDENCE_CLAIM: Final = (
    "Caller-declared M11-08 mechanism evidence dossier material; issuer authority "
    "is not authenticated."
)


class MechanismEvidenceSourceKind(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"
    UPSTREAM_VARIANT_PEPTIDE = "upstream_variant_peptide"
    QUALITY_SUPPORT = "quality_support"


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
    MISSING_SOURCE = "missing_source"
    QUALITY_UNRESOLVED = "quality_unresolved"
    CRITICAL_DISCREPANCY = "critical_discrepancy"
    OUT_OF_DOMAIN = "out_of_domain"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class MechanismEvidenceSource(FrozenModel):
    """Opaque, caller-declared source attribution."""

    source_id: Identifier
    kind: MechanismEvidenceSourceKind
    artifact: ArtifactReference
    claim: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1108_MAX_EVIDENCE)


class MechanismDossierAssumption(FrozenModel):
    assumption_id: Identifier
    statement: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1108_MAX_EVIDENCE)


class MechanismEvidenceLink(FrozenModel):
    """One reconstructable link in the mechanism evidence chain."""

    link_id: Identifier
    kind: MechanismEvidenceLinkKind
    assertion: NonEmptyStr
    predecessor_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1108_MAX_LINKS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1108_MAX_EVIDENCE)
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=64)


class CounterEvidenceRecord(FrozenModel):
    counter_evidence_id: Identifier
    statement: NonEmptyStr
    impact: NonEmptyStr
    challenges_link_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1108_MAX_LINKS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1108_MAX_EVIDENCE)


class ValidationRoute(FrozenModel):
    route_id: Identifier
    method: NonEmptyStr
    status: ValidationRouteStatus
    required_experiment: NonEmptyStr
    acceptance_criterion: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1108_MAX_EVIDENCE)


class ClaimCeiling(FrozenModel):
    maximum_claim: NonEmptyStr
    prohibited_interpretations: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1108_MAX_PROHIBITED_INTERPRETATIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1108_MAX_EVIDENCE)


class MechanismDossierConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: NonEmptyStr
    source_manifest: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1108_MAX_EVIDENCE
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1108_MAX_EVIDENCE)


class ReconstructionStep(FrozenModel):
    sequence: int = Field(ge=1, le=M1108_MAX_RECONSTRUCTION_STEPS)
    operation: NonEmptyStr
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=M1108_MAX_EVIDENCE)
    output_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1108_MAX_EVIDENCE)


class MechanismEvidenceDossier(FrozenModel):
    """Review-ready dossier with complete chain, challenge and claim ceiling."""

    dossier_id: Identifier
    version: SemanticVersion
    upstream_result: ArtifactReference
    sources: tuple[MechanismEvidenceSource, ...] = Field(min_length=1, max_length=M1108_MAX_SOURCES)
    assumptions: tuple[MechanismDossierAssumption, ...] = Field(
        min_length=1, max_length=M1108_MAX_ASSUMPTIONS
    )
    links: tuple[MechanismEvidenceLink, ...] = Field(min_length=1, max_length=M1108_MAX_LINKS)
    counter_evidence: tuple[CounterEvidenceRecord, ...] = Field(
        min_length=1, max_length=M1108_MAX_COUNTER_EVIDENCE
    )
    validation_routes: tuple[ValidationRoute, ...] = Field(
        min_length=1, max_length=M1108_MAX_VALIDATION_ROUTES
    )
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        min_length=1, max_length=M1108_MAX_RECONSTRUCTION_STEPS
    )
    uncertainty: UncertaintyProfile
    claim_ceiling: ClaimCeiling
    configuration: MechanismDossierConfiguration
    reviewer_id: Identifier
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1108_MAX_EVIDENCE)

    @model_validator(mode="after")
    def dossier_is_closed(self) -> MechanismEvidenceDossier:
        source_ids = tuple(item.source_id for item in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("mechanism evidence source ids must be unique")
        artifact_ids = tuple(item.artifact.artifact_id for item in self.sources)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("mechanism source artifacts must be unique")
        assumption_ids = tuple(item.assumption_id for item in self.assumptions)
        if len(assumption_ids) != len(set(assumption_ids)):
            raise ValueError("mechanism assumption ids must be unique")
        link_ids = tuple(item.link_id for item in self.links)
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("mechanism evidence link ids must be unique")
        counter_ids = tuple(item.counter_evidence_id for item in self.counter_evidence)
        if len(counter_ids) != len(set(counter_ids)):
            raise ValueError("counter-evidence ids must be unique")
        route_ids = tuple(item.route_id for item in self.validation_routes)
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("validation route ids must be unique")
        step_ids = tuple(item.sequence for item in self.reconstruction_steps)
        if len(step_ids) != len(set(step_ids)) or step_ids != tuple(sorted(step_ids)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        known = set(source_ids) | set(link_ids) | set(counter_ids) | set(route_ids)
        for counter in self.counter_evidence:
            if not set(counter.challenges_link_ids) <= set(link_ids):
                raise ValueError("counter-evidence references an unknown link")
        for link in self.links:
            if not set(link.predecessor_ids) <= known:
                raise ValueError("mechanism link references an unknown predecessor")
        if self.upstream_result.media_type != M1108_M1107_INPUT_MEDIA_TYPE:
            raise ValueError("dossier must bind the provisional M11-07 result media type")
        return self


class MechanismDossierDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: DossierDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1108_MAX_EVIDENCE)


class AssembleVariantPeptideMechanismDossierRequest(FrozenModel):
    """Provisional request ABI bound to the M11-07 upstream adjudication."""

    operation: Literal["assemble_variant_peptide_mechanism_dossier"] = M1108_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1108_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: MechanismDossierConfiguration
    source_artifacts: tuple[MechanismEvidenceSource, ...] = Field(
        min_length=1, max_length=M1108_MAX_SOURCES
    )
    assumptions: tuple[MechanismDossierAssumption, ...] = Field(
        min_length=1, max_length=M1108_MAX_ASSUMPTIONS
    )
    links: tuple[MechanismEvidenceLink, ...] = Field(min_length=1, max_length=M1108_MAX_LINKS)
    counter_evidence: tuple[CounterEvidenceRecord, ...] = Field(
        min_length=1, max_length=M1108_MAX_COUNTER_EVIDENCE
    )
    validation_routes: tuple[ValidationRoute, ...] = Field(
        min_length=1, max_length=M1108_MAX_VALIDATION_ROUTES
    )
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        min_length=1, max_length=M1108_MAX_RECONSTRUCTION_STEPS
    )
    reviewer_id: Identifier
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AssembleVariantPeptideMechanismDossierRequest:
        if self.upstream_result.media_type != M1108_M1107_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M11-07 adjudication result")
        source_ids = tuple(item.source_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source identifiers must be unique")
        artifact_ids = tuple(item.artifact.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("source artifacts must be unique")
        assumption_ids = tuple(item.assumption_id for item in self.assumptions)
        if len(assumption_ids) != len(set(assumption_ids)):
            raise ValueError("assumption identifiers must be unique")
        link_ids = tuple(item.link_id for item in self.links)
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("link identifiers must be unique")
        counter_ids = tuple(item.counter_evidence_id for item in self.counter_evidence)
        if len(counter_ids) != len(set(counter_ids)):
            raise ValueError("counter-evidence identifiers must be unique")
        route_ids = tuple(item.route_id for item in self.validation_routes)
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("validation route identifiers must be unique")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        known = set(source_ids) | set(link_ids) | set(counter_ids) | set(route_ids)
        if any(not set(link.predecessor_ids) <= known for link in self.links):
            raise ValueError("mechanism link references an unknown predecessor")
        if any(
            not set(counter.challenges_link_ids) <= set(link_ids)
            for counter in self.counter_evidence
        ):
            raise ValueError("counter-evidence references an unknown link")
        return self


class VariantPeptideMechanismDossierResult(FrozenModel):
    """Review-ready mechanism dossier with explicit claim ceiling and abstention."""

    output_type: Literal["variant_peptide_mechanism_evidence_dossier"] = (
        "variant_peptide_mechanism_evidence_dossier"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1108_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AssembleVariantPeptideMechanismDossierRequest
    status: MechanismDossierStatus
    dossier: MechanismEvidenceDossier | None = None
    diagnostics: tuple[MechanismDossierDiagnostic, ...] = Field(
        min_length=1, max_length=M1108_MAX_DIAGNOSTICS
    )
    findings: tuple[MechanismDossierFindingCode, ...] = Field(
        default=(), max_length=M1108_MAX_FINDINGS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant_peptide"] = M1108_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1108_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideMechanismDossierResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.m1108.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier does not bind the request digest")
        failed = {DossierDiagnosticStatus.FAIL, DossierDiagnosticStatus.NOT_EVALUABLE}
        if self.status is MechanismDossierStatus.READY:
            if (
                self.dossier is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed for item in self.diagnostics)
                or not self.human_review_required
            ):
                raise ValueError("ready result requires supported, reviewed dossier")
        elif (
            self.dossier is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no dossier and safe status")
        if self.provenance.module_id != M1108_MODULE_ID:
            raise ValueError("provenance must identify M11-08")
        if self.provenance.consent_state is not ConsentState.GRANTED:
            raise ValueError("result provenance must retain granted consent")
        if len(self.findings) != len(set(self.findings)):
            raise ValueError("findings must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, reviewed: bool = False) -> UncertaintyProfile:
    """Declare all seven dimensions when no calibrated estimator is executed."""

    suffix = " Review is required." if reviewed else ""
    rationale = "M11-08 does not estimate this dimension before owner-locked calibration." + suffix
    estimate = UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "No mechanistic claim is promoted by the provisional dossier assembler.",
        ),
    )


def expected_limitations(*, ready: bool) -> tuple[Limitation, ...]:
    limits = [
        Limitation(
            code="provisional_abi",
            statement="The M11-08 ABI is provisional and requires owner confirmation.",
        ),
        Limitation(
            code="caller_declared_evidence",
            statement="Evidence references are caller-declared and not authenticated here.",
        ),
        Limitation(
            code="no_prohibited_inference",
            statement=(
                "This module does not infer identity, consent, kinase activity, generic all-omics "
                "fusion, or treatment recommendation."
            ),
        ),
    ]
    if not ready:
        limits.append(
            Limitation(
                code="dossier_abstained",
                statement=(
                    "No dossier was emitted because reconstruction or support was unresolved."
                ),
            )
        )
    return tuple(limits)


def expected_provenance(
    context: ExecutionContext,
    *,
    input_digests: tuple[Sha256Digest, ...],
) -> ProvenanceRecord:
    """Project immutable context controls into module-local provenance."""

    refs = context.references
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
        activity_id=f"activity.m1108.{context.request_id}",
        actor_id=context.actor_id,
        module_id=M1108_MODULE_ID,
        module_version=M1108_CONTRACT_VERSION,
        generated_at=context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M1108_CONTRACT_VERSION",
    "M1108_EVIDENCE_CLAIM",
    "M1108_GATE",
    "M1108_M1107_INPUT_MEDIA_TYPE",
    "M1108_MAX_ASSUMPTIONS",
    "M1108_MAX_CANONICAL_REQUEST_BYTES",
    "M1108_MAX_CANONICAL_RESULT_BYTES",
    "M1108_MAX_COUNTER_EVIDENCE",
    "M1108_MAX_DIAGNOSTICS",
    "M1108_MAX_EVIDENCE",
    "M1108_MAX_FINDINGS",
    "M1108_MAX_LINKS",
    "M1108_MAX_PROHIBITED_INTERPRETATIONS",
    "M1108_MAX_RECONSTRUCTION_STEPS",
    "M1108_MAX_SOURCES",
    "M1108_MAX_VALIDATION_ROUTES",
    "M1108_MODULE_ID",
    "M1108_OPERATION",
    "M1108_OUTPUT_MEDIA_TYPE",
    "M1108_OWNER",
    "M1108_PARENT",
    "M1108_PROVISIONAL_ABI",
    "M1108_SAFETY_CLASS",
    "AssembleVariantPeptideMechanismDossierRequest",
    "ClaimCeiling",
    "CounterEvidenceRecord",
    "DossierDiagnosticStatus",
    "MechanismDossierAssumption",
    "MechanismDossierConfiguration",
    "MechanismDossierDiagnostic",
    "MechanismDossierFindingCode",
    "MechanismDossierStatus",
    "MechanismEvidenceDossier",
    "MechanismEvidenceLink",
    "MechanismEvidenceLinkKind",
    "MechanismEvidenceSource",
    "MechanismEvidenceSourceKind",
    "ReconstructionStep",
    "ValidationRoute",
    "ValidationRouteStatus",
    "VariantPeptideMechanismDossierResult",
    "expected_limitations",
    "expected_provenance",
    "expected_uncertainty",
]
