"""Provisional M10-08 evidence and explanation publisher contracts.

The M10-08 dossier requires attribution, diagnostics, assumptions,
counter-evidence, uncertainty, limitations, provenance, and reconstruction.
It does not freeze an operation, request/result names, schema inventory,
media type, endpoint, or the M10-07 handoff ABI.  Every symbol here is
reviewable scaffolding and is explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m10_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M10-08 dossier slice.
M1008_MODULE_ID: Final = "GLIO-PROTEOGEN-M10-08"
M1008_OPERATION: Final = "publish_protein_rna_evidence"
M1008_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1008_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-08+json"
M1008_M1007_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-07+json"
M1008_PARENT: Final = "protein_rna_discordance"
M1008_OWNER: Final = "Scientific engineering"
M1008_SAFETY_CLASS: Final = "S2"
M1008_GATE: Final = "G3"
M1008_PROVISIONAL_ABI: Final = True
M1008_MAX_SOURCES: Final = 64
M1008_MAX_ASSUMPTIONS: Final = 64
M1008_MAX_COUNTER_EVIDENCE: Final = 64
M1008_MAX_RECONSTRUCTION_STEPS: Final = 256
M1008_MAX_DIAGNOSTICS: Final = 128
M1008_MAX_EVIDENCE: Final = 64
M1008_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1008_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1008_EVIDENCE_CLAIM: Final = (
    "Caller-declared evidence for provisional M10-08 publication; issuer authority "
    "is not authenticated."
)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class EvidencePublicationStatus(StrEnum):
    PUBLISHED = "published"
    ABSTAINED = "abstained"


class ReconstructionStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_REPRODUCIBLE = "not_reproducible"


class PublisherFindingCode(StrEnum):
    UPSTREAM_ABSTAINED = "upstream_abstained"
    MISSING_ATTRIBUTION = "missing_attribution"
    RECONSTRUCTION_INCOMPLETE = "reconstruction_incomplete"
    COUNTER_EVIDENCE_UNRESOLVED = "counter_evidence_unresolved"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class PublisherDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class PublisherSourceKind(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"
    UPSTREAM_PROTEIN_RNA = "upstream_protein_rna_discordance"
    QUALITY_SUPPORT = "quality_support"


class PublisherEvidenceSource(FrozenModel):
    """One immutable input attribution; raw external payload is never traversed."""

    source_id: Identifier
    kind: PublisherSourceKind
    artifact: ArtifactReference
    claim: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1008_MAX_EVIDENCE)


class PublisherAssumption(FrozenModel):
    assumption_id: Identifier
    statement: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1008_MAX_EVIDENCE)


class PublisherCounterEvidence(FrozenModel):
    counter_evidence_id: Identifier
    statement: NonEmptyStr
    impact: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1008_MAX_EVIDENCE)


class ReconstructionStep(FrozenModel):
    sequence: int = Field(ge=1, le=M1008_MAX_RECONSTRUCTION_STEPS)
    operation: NonEmptyStr
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=M1008_MAX_EVIDENCE)
    output_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1008_MAX_EVIDENCE)


class PublisherDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: PublisherDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1008_MAX_EVIDENCE)


class ProteinRnaEvidenceBundle(FrozenModel):
    """Versioned evidence bundle with explicit reconstruction status."""

    bundle_id: Identifier
    version: SemanticVersion
    upstream_result: ArtifactReference
    sources: tuple[PublisherEvidenceSource, ...] = Field(min_length=1, max_length=M1008_MAX_SOURCES)
    assumptions: tuple[PublisherAssumption, ...] = Field(
        min_length=1, max_length=M1008_MAX_ASSUMPTIONS
    )
    counter_evidence: tuple[PublisherCounterEvidence, ...] = Field(
        min_length=1, max_length=M1008_MAX_COUNTER_EVIDENCE
    )
    uncertainty: UncertaintyProfile
    support_decision: SupportDecision
    reconstruction_status: ReconstructionStatus
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        min_length=1, max_length=M1008_MAX_RECONSTRUCTION_STEPS
    )
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1008_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> ProteinRnaEvidenceBundle:
        if self.upstream_result.media_type != M1008_M1007_RESULT_MEDIA_TYPE:
            raise ValueError("bundle must bind the provisional M10-07 result media type")
        source_ids = tuple(item.source_id for item in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence source identifiers must be unique")
        artifact_ids = tuple(item.artifact.artifact_id for item in self.sources)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("evidence source artifacts must be unique")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        if self.reconstruction_status is not ReconstructionStatus.COMPLETE:
            raise ValueError("published bundle requires complete reconstruction")
        return self


class ProteinRnaExplanation(FrozenModel):
    """Human-readable explanation object bound to one evidence bundle."""

    explanation_id: Identifier
    version: SemanticVersion
    bundle_id: Identifier
    summary: NonEmptyStr
    diagnostics: tuple[PublisherDiagnostic, ...] = Field(
        min_length=1, max_length=M1008_MAX_DIAGNOSTICS
    )
    assumptions: tuple[Identifier, ...] = Field(min_length=1, max_length=M1008_MAX_ASSUMPTIONS)
    counter_evidence: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M1008_MAX_COUNTER_EVIDENCE
    )
    reconstruction_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1008_MAX_EVIDENCE
    )

    @model_validator(mode="after")
    def explanation_is_closed(self) -> ProteinRnaExplanation:
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("diagnostic identifiers must be unique")
        if self.bundle_id == "":
            raise ValueError("explanation must bind a bundle")
        return self


class PublishProteinRnaEvidenceRequest(FrozenModel):
    """Provisional request ABI for evidence and explanation publication."""

    operation: Literal["publish_protein_rna_evidence"] = M1008_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1008_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    source_artifacts: tuple[PublisherEvidenceSource, ...] = Field(
        min_length=1, max_length=M1008_MAX_SOURCES
    )
    assumptions: tuple[PublisherAssumption, ...] = Field(
        default=(), max_length=M1008_MAX_ASSUMPTIONS
    )
    counter_evidence: tuple[PublisherCounterEvidence, ...] = Field(
        default=(), max_length=M1008_MAX_COUNTER_EVIDENCE
    )
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        default=(), max_length=M1008_MAX_RECONSTRUCTION_STEPS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> PublishProteinRnaEvidenceRequest:
        if self.upstream_result.media_type != M1008_M1007_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M10-07 result media type")
        source_ids = tuple(item.source_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("request evidence source identifiers must be unique")
        artifact_ids = tuple(item.artifact.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("request evidence source artifacts must be unique")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        return self


class ProteinRnaEvidencePublicationResult(FrozenModel):
    """Provisional publication result; abstention cannot masquerade as evidence."""

    output_type: Literal["protein_rna_evidence_explanation_publication"] = (
        "protein_rna_evidence_explanation_publication"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1008_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishProteinRnaEvidenceRequest
    status: EvidencePublicationStatus
    bundle: ProteinRnaEvidenceBundle | None = None
    explanation: ProteinRnaExplanation | None = None
    findings: tuple[PublisherFindingCode, ...] = Field(default=(), max_length=M1008_MAX_DIAGNOSTICS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1008_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1008_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaEvidencePublicationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.m1008.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier does not bind the request digest")
        if self.status is EvidencePublicationStatus.PUBLISHED:
            if (
                self.bundle is None
                or self.explanation is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.explanation.bundle_id != self.bundle.bundle_id
            ):
                raise ValueError("published result requires complete bundle and explanation")
        elif (
            self.bundle is not None
            or self.explanation is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no bundle, explanation, and safe status")
        if self.status is EvidencePublicationStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstention requires human review")
        if self.provenance.module_id != M1008_MODULE_ID:
            raise ValueError("provenance must identify M10-08")
        if self.provenance.consent_state is not ConsentState.GRANTED:
            raise ValueError("result provenance must retain the consent decision")
        if len(self.findings) != len(set(self.findings)):
            raise ValueError("findings must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return explicit uncertainty dimensions when no estimator is executed."""

    rationale = "M10-08 does not estimate this dimension before owner-locked calibration."
    estimate = UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("No scientific claim is promoted by the provisional publisher.",),
    )


def expected_limitations(*, published: bool) -> tuple[Limitation, ...]:
    """Return explicit interpretation ceilings for both publication states."""

    statements = [
        Limitation(
            code="provisional_abi",
            statement="The M10-08 ABI is provisional and requires owner confirmation.",
        ),
        Limitation(
            code="caller_declared_evidence",
            statement="Evidence references are caller-declared and not authenticated here.",
        ),
        Limitation(
            code="no_scientific_inference",
            statement=(
                "This publisher does not infer identity, consent, kinase activity, or treatment."
            ),
        ),
    ]
    if not published:
        statements.append(
            Limitation(
                code="publication_abstained",
                statement=(
                    "No evidence bundle or explanation was emitted because closure was incomplete."
                ),
            )
        )
    return tuple(statements)


def expected_provenance(
    context: ExecutionContext,
    *,
    input_digests: tuple[Sha256Digest, ...],
) -> ProvenanceRecord:
    """Project immutable context controls into module-local provenance."""

    references = context.references
    decisions = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1008.{context.request_id}",
        actor_id=context.actor_id,
        module_id=M1008_MODULE_ID,
        module_version=M1008_CONTRACT_VERSION,
        generated_at=context.occurred_at,
        input_digests=input_digests,
        configuration_digest=references.approved_configuration.evidence.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M1008_CONTRACT_VERSION",
    "M1008_EVIDENCE_CLAIM",
    "M1008_GATE",
    "M1008_M1007_RESULT_MEDIA_TYPE",
    "M1008_MAX_ASSUMPTIONS",
    "M1008_MAX_CANONICAL_REQUEST_BYTES",
    "M1008_MAX_CANONICAL_RESULT_BYTES",
    "M1008_MAX_COUNTER_EVIDENCE",
    "M1008_MAX_DIAGNOSTICS",
    "M1008_MAX_EVIDENCE",
    "M1008_MAX_RECONSTRUCTION_STEPS",
    "M1008_MAX_SOURCES",
    "M1008_MODULE_ID",
    "M1008_OPERATION",
    "M1008_OUTPUT_MEDIA_TYPE",
    "M1008_OWNER",
    "M1008_PARENT",
    "M1008_PROVISIONAL_ABI",
    "M1008_SAFETY_CLASS",
    "EvidencePublicationStatus",
    "ProteinRnaEvidenceBundle",
    "ProteinRnaEvidencePublicationResult",
    "ProteinRnaExplanation",
    "PublishProteinRnaEvidenceRequest",
    "PublisherAssumption",
    "PublisherCounterEvidence",
    "PublisherDiagnostic",
    "PublisherDiagnosticStatus",
    "PublisherEvidenceSource",
    "PublisherFindingCode",
    "PublisherSourceKind",
    "ReconstructionStatus",
    "ReconstructionStep",
    "expected_limitations",
    "expected_provenance",
    "expected_uncertainty",
]
