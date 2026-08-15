"""Provisional M09-08 evidence and explanation publisher contracts.

The M09-08 dossier requires attribution, diagnostics, assumptions,
counter-evidence, uncertainty, limitations, provenance, and reconstruction.
It does not freeze an operation, request/result names, schema inventory,
media type, endpoint, or the M09-07 handoff ABI.  Every symbol here is
reviewable scaffolding and is explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m09_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M09-08 dossier slice.
M0908_MODULE_ID: Final = "GLIO-PROTEOGEN-M09-08"
M0908_OPERATION: Final = "publish_complex_activity_evidence"
M0908_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0908_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-08+json"
M0908_M0907_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-07+json"
M0908_PARENT: Final = "complex_activity"
M0908_OWNER: Final = "Platform engineering"
M0908_SAFETY_CLASS: Final = "S2"
M0908_GATE: Final = "G3"
M0908_PROVISIONAL_ABI: Final = True
M0908_MAX_SOURCES: Final = 64
M0908_MAX_ASSUMPTIONS: Final = 64
M0908_MAX_COUNTER_EVIDENCE: Final = 64
M0908_MAX_RECONSTRUCTION_STEPS: Final = 256
M0908_MAX_DIAGNOSTICS: Final = 128
M0908_MAX_EVIDENCE: Final = 64
M0908_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0908_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0908_EVIDENCE_CLAIM: Final = (
    "Caller-declared evidence for provisional M09-08 publication; issuer authority "
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
    UPSTREAM_COMPLEX_ACTIVITY = "upstream_complex_activity"
    QUALITY_SUPPORT = "quality_support"


class PublisherEvidenceSource(FrozenModel):
    """One immutable input attribution; raw external payload is never traversed."""

    source_id: Identifier
    kind: PublisherSourceKind
    artifact: ArtifactReference
    claim: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0908_MAX_EVIDENCE)


class PublisherAssumption(FrozenModel):
    assumption_id: Identifier
    statement: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0908_MAX_EVIDENCE)


class PublisherCounterEvidence(FrozenModel):
    counter_evidence_id: Identifier
    statement: NonEmptyStr
    impact: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0908_MAX_EVIDENCE)


class ReconstructionStep(FrozenModel):
    sequence: int = Field(ge=1, le=M0908_MAX_RECONSTRUCTION_STEPS)
    operation: NonEmptyStr
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=M0908_MAX_EVIDENCE)
    output_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0908_MAX_EVIDENCE)


class PublisherDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: PublisherDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0908_MAX_EVIDENCE)


class ComplexActivityEvidenceBundle(FrozenModel):
    """Versioned evidence bundle with explicit reconstruction status."""

    bundle_id: Identifier
    version: SemanticVersion
    upstream_result: ArtifactReference
    sources: tuple[PublisherEvidenceSource, ...] = Field(
        min_length=1, max_length=M0908_MAX_SOURCES
    )
    assumptions: tuple[PublisherAssumption, ...] = Field(
        min_length=1, max_length=M0908_MAX_ASSUMPTIONS
    )
    counter_evidence: tuple[PublisherCounterEvidence, ...] = Field(
        min_length=1, max_length=M0908_MAX_COUNTER_EVIDENCE
    )
    uncertainty: UncertaintyProfile
    support_decision: SupportDecision
    reconstruction_status: ReconstructionStatus
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        min_length=1, max_length=M0908_MAX_RECONSTRUCTION_STEPS
    )
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0908_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> ComplexActivityEvidenceBundle:
        if self.upstream_result.media_type != M0908_M0907_RESULT_MEDIA_TYPE:
            raise ValueError("bundle must bind the provisional M09-07 result media type")
        source_ids = tuple(item.source_id for item in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence source identifiers must be unique")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        if self.reconstruction_status is not ReconstructionStatus.COMPLETE:
            raise ValueError("published bundle requires complete reconstruction")
        return self


class ComplexActivityExplanation(FrozenModel):
    """Human-readable explanation object bound to one evidence bundle."""

    explanation_id: Identifier
    version: SemanticVersion
    bundle_id: Identifier
    summary: NonEmptyStr
    diagnostics: tuple[PublisherDiagnostic, ...] = Field(
        min_length=1, max_length=M0908_MAX_DIAGNOSTICS
    )
    assumptions: tuple[Identifier, ...] = Field(min_length=1, max_length=M0908_MAX_ASSUMPTIONS)
    counter_evidence: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0908_MAX_COUNTER_EVIDENCE
    )
    reconstruction_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M0908_MAX_EVIDENCE
    )


class PublishComplexActivityEvidenceRequest(FrozenModel):
    """Provisional request ABI for evidence and explanation publication."""

    operation: Literal["publish_complex_activity_evidence"] = M0908_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0908_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    source_artifacts: tuple[PublisherEvidenceSource, ...] = Field(
        min_length=1, max_length=M0908_MAX_SOURCES
    )
    assumptions: tuple[PublisherAssumption, ...] = Field(
        default=(), max_length=M0908_MAX_ASSUMPTIONS
    )
    counter_evidence: tuple[PublisherCounterEvidence, ...] = Field(
        default=(), max_length=M0908_MAX_COUNTER_EVIDENCE
    )
    reconstruction_steps: tuple[ReconstructionStep, ...] = Field(
        default=(), max_length=M0908_MAX_RECONSTRUCTION_STEPS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> PublishComplexActivityEvidenceRequest:
        if self.upstream_result.media_type != M0908_M0907_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M09-07 result media type")
        source_ids = tuple(item.source_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("request evidence source identifiers must be unique")
        sequences = tuple(item.sequence for item in self.reconstruction_steps)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        return self


class ComplexActivityEvidencePublicationResult(FrozenModel):
    """Provisional publication result; abstention cannot masquerade as evidence."""

    output_type: Literal["complex_activity_evidence_explanation_publication"] = (
        "complex_activity_evidence_explanation_publication"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0908_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishComplexActivityEvidenceRequest
    status: EvidencePublicationStatus
    bundle: ComplexActivityEvidenceBundle | None = None
    explanation: ComplexActivityExplanation | None = None
    findings: tuple[PublisherFindingCode, ...] = Field(default=(), max_length=M0908_MAX_DIAGNOSTICS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M0908_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0908_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityEvidencePublicationResult:
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


__all__ = [
    "M0908_CONTRACT_VERSION",
    "M0908_EVIDENCE_CLAIM",
    "M0908_GATE",
    "M0908_M0907_RESULT_MEDIA_TYPE",
    "M0908_MAX_ASSUMPTIONS",
    "M0908_MAX_CANONICAL_REQUEST_BYTES",
    "M0908_MAX_CANONICAL_RESULT_BYTES",
    "M0908_MAX_COUNTER_EVIDENCE",
    "M0908_MAX_DIAGNOSTICS",
    "M0908_MAX_EVIDENCE",
    "M0908_MAX_RECONSTRUCTION_STEPS",
    "M0908_MAX_SOURCES",
    "M0908_MODULE_ID",
    "M0908_OPERATION",
    "M0908_OUTPUT_MEDIA_TYPE",
    "M0908_OWNER",
    "M0908_PARENT",
    "M0908_PROVISIONAL_ABI",
    "M0908_SAFETY_CLASS",
    "ComplexActivityEvidenceBundle",
    "ComplexActivityEvidencePublicationResult",
    "ComplexActivityExplanation",
    "EvidencePublicationStatus",
    "PublishComplexActivityEvidenceRequest",
    "PublisherAssumption",
    "PublisherCounterEvidence",
    "PublisherDiagnostic",
    "PublisherDiagnosticStatus",
    "PublisherEvidenceSource",
    "PublisherFindingCode",
    "PublisherSourceKind",
    "ReconstructionStatus",
    "ReconstructionStep",
]
