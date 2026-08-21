"""Provisional M18-03 fusion and aggregation engine contracts.

The M18-03 dossier requires component-specific integration that preserves
source identity, reliability, uncertainty, disagreement, and ownership.  The
ABI is provisional; unsupported or unresolved inputs abstain and never become
a negative finding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m18_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 6244-6284.
M1803_MODULE_ID: Final = "GLIO-PROTEOGEN-M18-03"
M1803_OPERATION: Final = "fuse_biomarker_panel_evidence"
M1803_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1803_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-03+json"
M1803_M1802_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-02+json"
M1803_PARENT: Final = "biomarker panel"
M1803_OWNER: Final = "ML engineering"
M1803_SAFETY_CLASS: Final = "S2"
M1803_GATE: Final = "G2"
M1803_PROVISIONAL_ABI: Final = True
M1803_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M1803_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:6244-6284"
M1803_MAX_CONTRIBUTIONS: Final = 128
M1803_MAX_DISAGREEMENTS: Final = 128
M1803_MAX_AGGREGATES: Final = 256
M1803_MAX_EVIDENCE: Final = 64
M1803_MAX_FINDINGS: Final = 64
M1803_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1803_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1803_EVIDENCE_CLAIM: Final = (
    "Caller-declared M18-03 source attribution, reliability, aggregation and "
    "disagreement material; issuer authority is not authenticated."
)


class SourceKind(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME = "genome"
    TRANSCRIPTOME = "transcriptome"
    PTM_ANNOTATION = "ptm_annotation"
    IDENTITY_LINEAGE = "identity_lineage"
    PROVENANCE = "provenance"
    CONSENT = "consent"
    QUALITY = "quality"
    SUPPORT = "support"
    INTENDED_USE = "intended_use"


class ReliabilityBand(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    NOT_EVALUABLE = "not_evaluable"


class DisagreementStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    NOT_EVALUABLE = "not_evaluable"


class FusionStatus(StrEnum):
    INTEGRATED = "integrated"
    ABSTAINED = "abstained"


class FusionFindingCode(StrEnum):
    INPUT_INCOMPLETE = "input_incomplete"
    SOURCE_DISAGREEMENT = "source_disagreement"
    LOW_RELIABILITY = "low_reliability"
    UNSUPPORTED_INPUT = "unsupported_input"
    OWNERSHIP_UNCLEAR = "ownership_unclear"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class SourceContribution(FrozenModel):
    """One attributable, reliability-scored component contribution."""

    source_id: Identifier
    kind: SourceKind
    owner: NonEmptyStr
    artifact: ArtifactReference
    claim: NonEmptyStr
    reliability_score: float = Field(ge=0.0, le=1.0)
    reliability_band: ReliabilityBand
    uncertainty_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1803_MAX_EVIDENCE)


class DisagreementRecord(FrozenModel):
    """A visible cross-source conflict that aggregation cannot erase."""

    disagreement_id: Identifier
    source_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=M1803_MAX_CONTRIBUTIONS)
    description: NonEmptyStr
    status: DisagreementStatus
    resolution: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1803_MAX_EVIDENCE)

    @model_validator(mode="after")
    def resolution_matches_status(self) -> DisagreementRecord:
        if self.status is DisagreementStatus.RESOLVED and self.resolution is None:
            raise ValueError("resolved disagreement requires a resolution")
        if self.status is not DisagreementStatus.RESOLVED and self.resolution is not None:
            raise ValueError("unresolved disagreement cannot carry a resolution")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("disagreement source ids must be unique")
        return self


class AggregationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    reliability_threshold: float = Field(ge=0.0, le=1.0)
    component_specific: Literal[True] = True
    preserve_source_identity: Literal[True] = True
    preserve_disagreement: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1803_MAX_EVIDENCE)


class IntegratedEvidenceObject(FrozenModel):
    """Attributable integrated evidence with reliability and conflicts."""

    integrated_id: Identifier
    version: SemanticVersion
    aggregate_claim: NonEmptyStr
    contributions: tuple[SourceContribution, ...] = Field(
        min_length=1, max_length=M1803_MAX_CONTRIBUTIONS
    )
    disagreements: tuple[DisagreementRecord, ...] = Field(
        default=(), max_length=M1803_MAX_DISAGREEMENTS
    )
    aggregate_values: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1803_MAX_AGGREGATES)
    configuration: AggregationConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1803_MAX_EVIDENCE)

    @model_validator(mode="after")
    def object_is_closed(self) -> IntegratedEvidenceObject:
        source_ids = tuple(item.source_id for item in self.contributions)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source contribution ids must be unique")
        allowed = set(source_ids)
        for disagreement in self.disagreements:
            if not set(disagreement.source_ids) <= allowed:
                raise ValueError("disagreement references an unknown source")
        return self


class FusionFinding(FrozenModel):
    finding_id: Identifier
    code: FusionFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1803_MAX_EVIDENCE)


class FuseBiomarkerPanelEvidenceRequest(FrozenModel):
    """Provisional request bound to the M18-02 alignment result."""

    operation: Literal["fuse_biomarker_panel_evidence"] = M1803_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1803_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    alignment_result: ArtifactReference
    contributions: tuple[SourceContribution, ...] = Field(
        min_length=1, max_length=M1803_MAX_CONTRIBUTIONS
    )
    disagreements: tuple[DisagreementRecord, ...] = Field(
        default=(), max_length=M1803_MAX_DISAGREEMENTS
    )
    aggregate_values: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1803_MAX_AGGREGATES)
    configuration: AggregationConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1803_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> FuseBiomarkerPanelEvidenceRequest:
        if self.alignment_result.media_type != M1803_M1802_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M18-02 alignment result")
        source_ids = tuple(item.source_id for item in self.contributions)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("request source contribution ids must be unique")
        allowed = set(source_ids)
        if any(not set(item.source_ids) <= allowed for item in self.disagreements):
            raise ValueError("request disagreement references an unknown source")
        return self


class BiomarkerPanelIntegratedEvidenceResult(FrozenModel):
    """Integrated evidence result with explicit attribution and abstention."""

    output_type: Literal["biomarker_panel_integrated_evidence"] = (
        "biomarker_panel_integrated_evidence"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1803_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: FuseBiomarkerPanelEvidenceRequest
    status: FusionStatus
    integrated_evidence: IntegratedEvidenceObject | None = None
    findings: tuple[FusionFinding, ...] = Field(default=(), max_length=M1803_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M1803_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1803_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelIntegratedEvidenceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        has_unsafe_source = any(
            item.reliability_band is ReliabilityBand.NOT_EVALUABLE
            for item in self.request.contributions
        )
        if self.status is FusionStatus.INTEGRATED:
            if (
                self.integrated_evidence is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
                or has_unsafe_source
            ):
                raise ValueError("integrated result requires review-only attributable sources")
        elif (
            self.integrated_evidence is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no integrated object and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1803_CONTRACT_VERSION",
    "M1803_DOSSIER_SHA256",
    "M1803_DOSSIER_SLICE",
    "M1803_EVIDENCE_CLAIM",
    "M1803_GATE",
    "M1803_M1802_INPUT_MEDIA_TYPE",
    "M1803_MAX_AGGREGATES",
    "M1803_MAX_CANONICAL_REQUEST_BYTES",
    "M1803_MAX_CANONICAL_RESULT_BYTES",
    "M1803_MAX_CONTRIBUTIONS",
    "M1803_MAX_DISAGREEMENTS",
    "M1803_MAX_EVIDENCE",
    "M1803_MAX_FINDINGS",
    "M1803_MODULE_ID",
    "M1803_OPERATION",
    "M1803_OUTPUT_MEDIA_TYPE",
    "M1803_OWNER",
    "M1803_PARENT",
    "M1803_PROVISIONAL_ABI",
    "M1803_SAFETY_CLASS",
    "AggregationConfiguration",
    "BiomarkerPanelIntegratedEvidenceResult",
    "DisagreementRecord",
    "DisagreementStatus",
    "FuseBiomarkerPanelEvidenceRequest",
    "FusionFinding",
    "FusionFindingCode",
    "FusionStatus",
    "IntegratedEvidenceObject",
    "ReliabilityBand",
    "SourceContribution",
    "SourceKind",
]
