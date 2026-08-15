"""Provisional M08-08 evidence and explanation publisher contracts.

The dossier requires complete sources, assumptions, counter-evidence,
uncertainty, limitations, provenance, and reconstruction material.  It does
not freeze the public ABI or publisher format; all symbols remain provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m08_08.canonical import (
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

M0808_MODULE_ID: Final = "GLIO-PROTEOGEN-M08-08"
M0808_OPERATION: Final = "publish_transcript_protein_evidence_explanation"
M0808_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0808_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-08+json"
M0808_CALIBRATION_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-07+json"
M0808_UNCERTAINTY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-06+json"
M0808_PARENT: Final = "protein_subtype"
M0808_OWNER: Final = "Data engineering"
M0808_SAFETY_CLASS: Final = "S2"
M0808_GATE: Final = "G3"
M0808_PROVISIONAL_ABI: Final = True
M0808_MAX_ITEMS: Final = 256
M0808_MAX_EVIDENCE: Final = 64
M0808_MAX_RECONSTRUCTION_STEPS: Final = 128
M0808_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0808_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0808_EVIDENCE_CLAIM: Final = (
    "Caller-declared evidence and explanation material; issuer authority is not authenticated."
)


class EvidenceRole(StrEnum):
    INPUT = "input"
    DIAGNOSTIC = "diagnostic"
    ASSUMPTION = "assumption"
    COUNTER_EVIDENCE = "counter_evidence"
    RECONSTRUCTION = "reconstruction"


class PublisherStatus(StrEnum):
    PUBLISHED = "published"
    ABSTAINED = "abstained"


class PublisherDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class ReconstructionStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NOT_EVALUABLE = "not_evaluable"


class PublishedEvidenceItem(FrozenModel):
    evidence_id: Identifier
    role: EvidenceRole
    artifact: ArtifactReference
    claim: NonEmptyStr
    required: bool = True


class ExplanationAssumption(FrozenModel):
    assumption_id: Identifier
    statement: NonEmptyStr
    evidence_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0808_MAX_EVIDENCE
    )


class ExplanationDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: PublisherDiagnosticStatus
    message: NonEmptyStr
    evidence_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M0808_MAX_EVIDENCE
    )


class ReconstructionStep(FrozenModel):
    sequence: int = Field(ge=1, le=M0808_MAX_RECONSTRUCTION_STEPS)
    operation: NonEmptyStr
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=M0808_MAX_EVIDENCE)
    output_digest: Sha256Digest
    status: ReconstructionStatus
    evidence_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0808_MAX_EVIDENCE
    )


class EvidenceBundle(FrozenModel):
    """Complete, reconstructable evidence projection for one published result."""

    bundle_id: Identifier
    version: SemanticVersion
    items: tuple[PublishedEvidenceItem, ...] = Field(
        min_length=1, max_length=M0808_MAX_ITEMS
    )
    assumptions: tuple[ExplanationAssumption, ...] = Field(
        min_length=1, max_length=M0808_MAX_ITEMS
    )
    counter_evidence: tuple[PublishedEvidenceItem, ...] = Field(
        min_length=1, max_length=M0808_MAX_ITEMS
    )
    reconstruction: tuple[ReconstructionStep, ...] = Field(
        min_length=1, max_length=M0808_MAX_RECONSTRUCTION_STEPS
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0808_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> EvidenceBundle:
        ids = tuple(item.evidence_id for item in self.items)
        ids += tuple(item.evidence_id for item in self.counter_evidence)
        if len(ids) != len(set(ids)):
            raise ValueError("evidence item ids must be unique")
        sequences = tuple(item.sequence for item in self.reconstruction)
        if len(sequences) != len(set(sequences)) or sequences != tuple(sorted(sequences)):
            raise ValueError("reconstruction steps must have unique ordered sequences")
        if any(item.role is not EvidenceRole.COUNTER_EVIDENCE for item in self.counter_evidence):
            raise ValueError("counter-evidence collection must contain counter-evidence items")
        return self


class ExplanationObject(FrozenModel):
    explanation_id: Identifier
    version: SemanticVersion
    summary: NonEmptyStr
    diagnostics: tuple[ExplanationDiagnostic, ...] = Field(
        min_length=1, max_length=M0808_MAX_ITEMS
    )
    limitation_statements: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M0808_MAX_ITEMS
    )
    bundle_id: Identifier


class PublishTranscriptProteinEvidenceRequest(FrozenModel):
    """Provisional request bound to M08-07 calibration and M08-06 uncertainty."""

    operation: Literal["publish_transcript_protein_evidence_explanation"] = M0808_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0808_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    calibration_result: ArtifactReference
    uncertainty_result: ArtifactReference
    evidence_bundle: EvidenceBundle
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0808_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> PublishTranscriptProteinEvidenceRequest:
        if self.calibration_result.media_type != M0808_CALIBRATION_MEDIA_TYPE:
            raise ValueError("publisher request must bind the provisional M08-07 result")
        if self.uncertainty_result.media_type != M0808_UNCERTAINTY_MEDIA_TYPE:
            raise ValueError("publisher request must bind the provisional M08-06 result")
        return self


class PublishTranscriptProteinEvidenceResult(FrozenModel):
    """Versioned evidence bundle and explanation with fail-closed publication."""

    output_type: Literal["transcript_protein_evidence_explanation"] = (
        "transcript_protein_evidence_explanation"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0808_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishTranscriptProteinEvidenceRequest
    status: PublisherStatus
    evidence_bundle: EvidenceBundle | None = None
    explanation: ExplanationObject | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M0808_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0808_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> PublishTranscriptProteinEvidenceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is PublisherStatus.PUBLISHED:
            if (
                self.evidence_bundle is None
                or self.explanation is None
                or self.explanation.bundle_id != self.evidence_bundle.bundle_id
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("published result requires complete supported evidence")
        elif (
            self.evidence_bundle is not None
            or self.explanation is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no published evidence and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0808_CALIBRATION_MEDIA_TYPE",
    "M0808_CONTRACT_VERSION",
    "M0808_EVIDENCE_CLAIM",
    "M0808_GATE",
    "M0808_MAX_CANONICAL_REQUEST_BYTES",
    "M0808_MAX_CANONICAL_RESULT_BYTES",
    "M0808_MAX_EVIDENCE",
    "M0808_MAX_ITEMS",
    "M0808_MAX_RECONSTRUCTION_STEPS",
    "M0808_MODULE_ID",
    "M0808_OPERATION",
    "M0808_OUTPUT_MEDIA_TYPE",
    "M0808_OWNER",
    "M0808_PARENT",
    "M0808_PROVISIONAL_ABI",
    "M0808_SAFETY_CLASS",
    "M0808_UNCERTAINTY_MEDIA_TYPE",
    "EvidenceBundle",
    "EvidenceRole",
    "ExplanationAssumption",
    "ExplanationDiagnostic",
    "ExplanationObject",
    "PublishTranscriptProteinEvidenceRequest",
    "PublishTranscriptProteinEvidenceResult",
    "PublishedEvidenceItem",
    "PublisherDiagnosticStatus",
    "PublisherStatus",
    "ReconstructionStatus",
    "ReconstructionStep",
]
