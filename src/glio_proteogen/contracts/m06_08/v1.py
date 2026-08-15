"""Provisional M06-08 evidence and explanation publisher contracts.

The dossier requires sources, assumptions, uncertainty, support status,
counter-evidence, diagnostics, and reconstruction evidence.  It does not
freeze an operation, request/result names, schema inventory, media type,
endpoint, or explanation vocabulary.  All ABI symbols here are provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m06_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M06-08 dossier slice.
M0608_MODULE_ID: Final = "GLIO-PROTEOGEN-M06-08"
M0608_OPERATION: Final = "publish_protein_abundance_evidence"
M0608_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0608_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m06-08+json"
M0608_PARENT: Final = "biomarker_panel"
M0608_OWNER: Final = "Quality engineering"
M0608_SAFETY_CLASS: Final = "S2"
M0608_GATE: Final = "G3"
M0608_MAX_SOURCES: Final = 64
M0608_MAX_ASSUMPTIONS: Final = 64
M0608_MAX_COUNTER_EVIDENCE: Final = 64
M0608_MAX_RECONSTRUCTION_STEPS: Final = 256
M0608_MAX_DIAGNOSTICS: Final = 128
M0608_MAX_EVIDENCE: Final = 64
M0608_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0608_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0608_M0607_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m06-07+json"
M0608_EVIDENCE_CLAIM: Final = (
    "Caller-declared evidence for provisional M06-08 publication; issuer authority "
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


class PublisherAssumption(FrozenModel):
    assumption_id: Identifier
    statement: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0608_MAX_EVIDENCE)


class PublisherCounterEvidence(FrozenModel):
    counter_evidence_id: Identifier
    statement: NonEmptyStr
    impact: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0608_MAX_EVIDENCE)


class ReconstructionStep(FrozenModel):
    sequence: int = Field(ge=1, le=M0608_MAX_RECONSTRUCTION_STEPS)
    operation: NonEmptyStr
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=M0608_MAX_EVIDENCE)
    output_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0608_MAX_EVIDENCE)


class PublisherDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: PublisherDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0608_MAX_EVIDENCE)


class ProteinAbundanceEvidenceBundle(FrozenModel):
    """Versioned evidence bundle with explicit reconstruction status."""

    bundle_id: Identifier
    version: SemanticVersion
    upstream_result: ArtifactReference
    sources: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0608_MAX_SOURCES)
    assumptions: tuple[PublisherAssumption, ...] = Field(
        min_length=1, max_length=M0608_MAX_ASSUMPTIONS
    )
    counter_evidence: tuple[PublisherCounterEvidence, ...] = Field(
        min_length=1, max_length=M0608_MAX_COUNTER_EVIDENCE
    )
    uncertainty: UncertaintyProfile
    support_decision: SupportDecision
    reconstruction_status: ReconstructionStatus
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        min_length=1, max_length=M0608_MAX_RECONSTRUCTION_STEPS
    )
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0608_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> ProteinAbundanceEvidenceBundle:
        if self.upstream_result.media_type != M0608_M0607_RESULT_MEDIA_TYPE:
            raise ValueError("bundle must bind the provisional M06-07 result media type")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        if self.reconstruction_status is not ReconstructionStatus.COMPLETE:
            raise ValueError("published bundle requires complete reconstruction")
        return self


class ProteinAbundanceExplanation(FrozenModel):
    """Human-readable explanation object bound to one evidence bundle."""

    explanation_id: Identifier
    version: SemanticVersion
    bundle_id: Identifier
    summary: NonEmptyStr
    diagnostics: tuple[PublisherDiagnostic, ...] = Field(
        min_length=1, max_length=M0608_MAX_DIAGNOSTICS
    )
    assumptions: tuple[Identifier, ...] = Field(min_length=1, max_length=M0608_MAX_ASSUMPTIONS)
    counter_evidence: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0608_MAX_COUNTER_EVIDENCE
    )
    reconstruction_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M0608_MAX_EVIDENCE
    )


class PublishProteinAbundanceEvidenceRequest(FrozenModel):
    """Provisional request ABI for evidence and explanation publication."""

    operation: Literal["publish_protein_abundance_evidence"] = M0608_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0608_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0608_MAX_SOURCES
    )
    assumptions: tuple[PublisherAssumption, ...] = Field(
        default=(), max_length=M0608_MAX_ASSUMPTIONS
    )
    counter_evidence: tuple[PublisherCounterEvidence, ...] = Field(
        default=(), max_length=M0608_MAX_COUNTER_EVIDENCE
    )
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        default=(), max_length=M0608_MAX_RECONSTRUCTION_STEPS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> PublishProteinAbundanceEvidenceRequest:
        if self.upstream_result.media_type != M0608_M0607_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M06-07 result media type")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        return self


class ProteinAbundanceEvidencePublicationResult(FrozenModel):
    """Provisional publication result; abstention cannot masquerade as evidence."""

    output_type: Literal["protein_abundance_evidence_publication"] = (
        "protein_abundance_evidence_publication"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0608_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishProteinAbundanceEvidenceRequest
    status: EvidencePublicationStatus
    bundle: ProteinAbundanceEvidenceBundle | None = None
    explanation: ProteinAbundanceExplanation | None = None
    findings: tuple[PublisherFindingCode, ...] = Field(default=(), max_length=M0608_MAX_DIAGNOSTICS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker_panel"] = M0608_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0608_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinAbundanceEvidencePublicationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
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
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return a seven-dimension non-estimable profile for safe publication abstention."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="The provisional M06-08 publisher has no owner-confirmed reconstruction gate.",
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
            "Uncertainty is not published until sources, assumptions, counter-evidence, "
            "and reconstruction are owner-locked.",
        ),
    )


def expected_provenance(
    request: PublishProteinAbundanceEvidenceRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project all seven caller controls into module-local provenance."""

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
        module_id=M0608_MODULE_ID,
        module_version=M0608_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M0608_CONTRACT_VERSION",
    "M0608_EVIDENCE_CLAIM",
    "M0608_GATE",
    "M0608_M0607_RESULT_MEDIA_TYPE",
    "M0608_MAX_ASSUMPTIONS",
    "M0608_MAX_CANONICAL_REQUEST_BYTES",
    "M0608_MAX_CANONICAL_RESULT_BYTES",
    "M0608_MAX_COUNTER_EVIDENCE",
    "M0608_MAX_DIAGNOSTICS",
    "M0608_MAX_EVIDENCE",
    "M0608_MAX_RECONSTRUCTION_STEPS",
    "M0608_MAX_SOURCES",
    "M0608_MODULE_ID",
    "M0608_OPERATION",
    "M0608_OUTPUT_MEDIA_TYPE",
    "M0608_OWNER",
    "M0608_PARENT",
    "M0608_SAFETY_CLASS",
    "EvidencePublicationStatus",
    "ProteinAbundanceEvidenceBundle",
    "ProteinAbundanceEvidencePublicationResult",
    "ProteinAbundanceExplanation",
    "PublishProteinAbundanceEvidenceRequest",
    "PublisherAssumption",
    "PublisherCounterEvidence",
    "PublisherDiagnostic",
    "PublisherDiagnosticStatus",
    "PublisherFindingCode",
    "ReconstructionStatus",
    "ReconstructionStep",
    "expected_provenance",
    "expected_uncertainty",
]
