"""Provisional M07-08 evidence and explanation publisher contracts.

The M07-08 dossier requires attribution, diagnostics, assumptions,
counter-evidence, uncertainty, limitations, provenance, and reconstruction.
It does not freeze an operation, request/result names, schema inventory,
media type, endpoint, or the M07-07 handoff ABI.  Every symbol here is
reviewable scaffolding and is explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m07_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M07-08 dossier slice.
M0708_MODULE_ID: Final = "GLIO-PROTEOGEN-M07-08"
M0708_OPERATION: Final = "publish_proteotype_evidence"
M0708_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0708_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-08+json"
M0708_PARENT: Final = "proteotype"
M0708_OWNER: Final = "Clinical science"
M0708_SAFETY_CLASS: Final = "S2"
M0708_GATE: Final = "G3"
M0708_MAX_SOURCES: Final = 64
M0708_MAX_ASSUMPTIONS: Final = 64
M0708_MAX_COUNTER_EVIDENCE: Final = 64
M0708_MAX_RECONSTRUCTION_STEPS: Final = 256
M0708_MAX_DIAGNOSTICS: Final = 128
M0708_MAX_EVIDENCE: Final = 64
M0708_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0708_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0708_M0707_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-07+json"
M0708_EVIDENCE_CLAIM: Final = (
    "Caller-declared evidence for provisional M07-08 publication; issuer authority "
    "is not authenticated."
)


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
    UPSTREAM_PROTEOTYPE = "upstream_proteotype"
    QUALITY_SUPPORT = "quality_support"


class PublisherEvidenceSource(FrozenModel):
    """One immutable input attribution; raw external payload is never traversed."""

    source_id: Identifier
    kind: PublisherSourceKind
    artifact: ArtifactReference
    claim: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0708_MAX_EVIDENCE)

    @model_validator(mode="after")
    def source_evidence_is_positive(self) -> PublisherEvidenceSource:
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("source evidence must use the evidence role")
        return self


class PublisherAssumption(FrozenModel):
    assumption_id: Identifier
    statement: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0708_MAX_EVIDENCE)

    @model_validator(mode="after")
    def assumption_evidence_is_positive(self) -> PublisherAssumption:
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("assumption evidence must use the evidence role")
        return self


class PublisherCounterEvidence(FrozenModel):
    counter_evidence_id: Identifier
    statement: NonEmptyStr
    impact: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0708_MAX_EVIDENCE)

    @model_validator(mode="after")
    def counter_evidence_is_explicit(self) -> PublisherCounterEvidence:
        if any(item.role != "counter_evidence" for item in self.evidence):
            raise ValueError("counter-evidence references must use the counter_evidence role")
        return self


class ReconstructionStep(FrozenModel):
    sequence: int = Field(ge=1, le=M0708_MAX_RECONSTRUCTION_STEPS)
    operation: NonEmptyStr
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=M0708_MAX_EVIDENCE)
    output_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0708_MAX_EVIDENCE)

    @model_validator(mode="after")
    def reconstruction_evidence_is_positive(self) -> ReconstructionStep:
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("reconstruction evidence must use the evidence role")
        return self


class PublisherDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: PublisherDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0708_MAX_EVIDENCE)

    @model_validator(mode="after")
    def diagnostic_evidence_is_explicit(self) -> PublisherDiagnostic:
        if any(item.role not in {"evidence", "counter_evidence"} for item in self.evidence):
            raise ValueError("diagnostic evidence has an invalid role")
        return self


class ProteotypeEvidenceBundle(FrozenModel):
    """Versioned evidence bundle with explicit reconstruction status."""

    bundle_id: Identifier
    version: SemanticVersion
    upstream_result: ArtifactReference
    sources: tuple[PublisherEvidenceSource, ...] = Field(
        min_length=1, max_length=M0708_MAX_SOURCES
    )
    assumptions: tuple[PublisherAssumption, ...] = Field(
        min_length=1, max_length=M0708_MAX_ASSUMPTIONS
    )
    counter_evidence: tuple[PublisherCounterEvidence, ...] = Field(
        min_length=1, max_length=M0708_MAX_COUNTER_EVIDENCE
    )
    uncertainty: UncertaintyProfile
    support_decision: SupportDecision
    reconstruction_status: ReconstructionStatus
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        min_length=1, max_length=M0708_MAX_RECONSTRUCTION_STEPS
    )
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0708_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> ProteotypeEvidenceBundle:
        if self.upstream_result.media_type != M0708_M0707_RESULT_MEDIA_TYPE:
            raise ValueError("bundle must bind the provisional M07-07 result media type")
        source_ids = tuple(item.source_id for item in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence source identifiers must be unique")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        if self.reconstruction_status is not ReconstructionStatus.COMPLETE:
            raise ValueError("published bundle requires complete reconstruction")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("bundle evidence must use the evidence role")
        artifact_ids = tuple(item.artifact.artifact_id for item in self.sources)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("evidence sources must not repeat artifact identifiers")
        return self


class ProteotypeExplanation(FrozenModel):
    """Human-readable explanation object bound to one evidence bundle."""

    explanation_id: Identifier
    version: SemanticVersion
    bundle_id: Identifier
    summary: NonEmptyStr
    diagnostics: tuple[PublisherDiagnostic, ...] = Field(
        min_length=1, max_length=M0708_MAX_DIAGNOSTICS
    )
    assumptions: tuple[Identifier, ...] = Field(min_length=1, max_length=M0708_MAX_ASSUMPTIONS)
    counter_evidence: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0708_MAX_COUNTER_EVIDENCE
    )
    reconstruction_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M0708_MAX_EVIDENCE
    )


class PublishProteotypeEvidenceRequest(FrozenModel):
    """Provisional request ABI for evidence and explanation publication."""

    operation: Literal["publish_proteotype_evidence"] = M0708_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0708_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    source_artifacts: tuple[PublisherEvidenceSource, ...] = Field(
        min_length=1, max_length=M0708_MAX_SOURCES
    )
    assumptions: tuple[PublisherAssumption, ...] = Field(
        default=(), max_length=M0708_MAX_ASSUMPTIONS
    )
    counter_evidence: tuple[PublisherCounterEvidence, ...] = Field(
        default=(), max_length=M0708_MAX_COUNTER_EVIDENCE
    )
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        default=(), max_length=M0708_MAX_RECONSTRUCTION_STEPS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> PublishProteotypeEvidenceRequest:
        if self.upstream_result.media_type != M0708_M0707_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M07-07 result media type")
        source_ids = tuple(item.source_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("request evidence source identifiers must be unique")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        artifact_ids = tuple(item.artifact.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("request evidence sources must have unique artifact identifiers")
        assumption_ids = tuple(item.assumption_id for item in self.assumptions)
        counter_ids = tuple(item.counter_evidence_id for item in self.counter_evidence)
        if len(assumption_ids) != len(set(assumption_ids)):
            raise ValueError("assumptions must have unique identifiers")
        if len(counter_ids) != len(set(counter_ids)):
            raise ValueError("counter-evidence must have unique identifiers")
        return self


class ProteotypeEvidencePublicationResult(FrozenModel):
    """Provisional publication result; abstention cannot masquerade as evidence."""

    output_type: Literal["proteotype_evidence_explanation_publication"] = (
        "proteotype_evidence_explanation_publication"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0708_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishProteotypeEvidenceRequest
    status: EvidencePublicationStatus
    bundle: ProteotypeEvidenceBundle | None = None
    explanation: ProteotypeExplanation | None = None
    findings: tuple[PublisherFindingCode, ...] = Field(default=(), max_length=M0708_MAX_DIAGNOSTICS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M0708_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0708_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeEvidencePublicationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if not self.evidence:
            raise ValueError("every result requires reconstruction-visible evidence references")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("result evidence must use the evidence role")
        if self.status is EvidencePublicationStatus.PUBLISHED:
            if (
                self.bundle is None
                or self.explanation is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
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
            raise ValueError("abstention requires human review acknowledgement")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return explicit non-estimable uncertainty until the publisher is owner-locked."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M07-08 cannot quantify uncertainty until attribution, reconstruction, "
            "and owner-approved publication policy are locked."
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
            "No unsupported or missing evidence is converted into a negative finding.",
        ),
    )


def expected_provenance(
    request: PublishProteotypeEvidenceRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project all seven caller-declared controls into auditable provenance."""

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
        module_id=M0708_MODULE_ID,
        module_version=M0708_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.upstream_result.digest,
            *(source.artifact.digest for source in request.source_artifacts),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M0708_CONTRACT_VERSION",
    "M0708_EVIDENCE_CLAIM",
    "M0708_GATE",
    "M0708_M0707_RESULT_MEDIA_TYPE",
    "M0708_MAX_ASSUMPTIONS",
    "M0708_MAX_CANONICAL_REQUEST_BYTES",
    "M0708_MAX_CANONICAL_RESULT_BYTES",
    "M0708_MAX_COUNTER_EVIDENCE",
    "M0708_MAX_DIAGNOSTICS",
    "M0708_MAX_EVIDENCE",
    "M0708_MAX_RECONSTRUCTION_STEPS",
    "M0708_MAX_SOURCES",
    "M0708_MODULE_ID",
    "M0708_OPERATION",
    "M0708_OUTPUT_MEDIA_TYPE",
    "M0708_OWNER",
    "M0708_PARENT",
    "M0708_SAFETY_CLASS",
    "EvidencePublicationStatus",
    "ProteotypeEvidenceBundle",
    "ProteotypeEvidencePublicationResult",
    "ProteotypeExplanation",
    "PublishProteotypeEvidenceRequest",
    "PublisherAssumption",
    "PublisherCounterEvidence",
    "PublisherDiagnostic",
    "PublisherDiagnosticStatus",
    "PublisherEvidenceSource",
    "PublisherFindingCode",
    "PublisherSourceKind",
    "ReconstructionStatus",
    "ReconstructionStep",
    "expected_provenance",
    "expected_uncertainty",
]
