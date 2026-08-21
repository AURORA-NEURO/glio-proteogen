"""Provisional M20-03 fusion and aggregation engine contracts.

M20-03 owns component-specific integration beneath Biomarker-panel
translation. The contract preserves source identity, reliability, uncertainty,
disagreement, and ownership while abstaining on unsupported inputs.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m20_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 6964-7004.
M2003_MODULE_ID: Final = "GLIO-PROTEOGEN-M20-03"
M2003_OPERATION: Final = "fuse_protein_subtype_evidence"
M2003_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2003_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-03+json"
M2003_M2002_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-02+json"
M2003_PARENT: Final = "protein subtype"
M2003_OWNER: Final = "Clinical science"
M2003_SAFETY_CLASS: Final = "S2"
M2003_GATE: Final = "G2"
M2003_PROVISIONAL_ABI: Final = True
M2003_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2003_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:6964-7004"
M2003_MAX_CONTRIBUTIONS: Final = 128
M2003_MAX_DISAGREEMENTS: Final = 128
M2003_MAX_AGGREGATES: Final = 256
M2003_MAX_EVIDENCE: Final = 64
M2003_MAX_FINDINGS: Final = 64
M2003_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2003_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2003_EVIDENCE_CLAIM: Final = (
    "Caller-declared M20-03 source attribution, reliability, aggregation and "
    "disagreement material; issuer authority is not authenticated."
)
_HIGH_RELIABILITY_THRESHOLD: Final = 0.8
_MODERATE_RELIABILITY_THRESHOLD: Final = 0.5


class SourceKind(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME = "genome"
    TRANSCRIPTOME = "transcriptome"
    PTM_ANNOTATION = "ptm_annotation"
    BIOMARKER_PANEL_TRANSLATION = "biomarker_panel_translation"
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2003_MAX_EVIDENCE)

    @model_validator(mode="after")
    def reliability_band_matches_score(self) -> SourceContribution:
        expected = (
            ReliabilityBand.HIGH
            if self.reliability_score >= _HIGH_RELIABILITY_THRESHOLD
            else ReliabilityBand.MODERATE
            if self.reliability_score >= _MODERATE_RELIABILITY_THRESHOLD
            else ReliabilityBand.LOW
        )
        if self.reliability_band is ReliabilityBand.NOT_EVALUABLE:
            if self.reliability_score != 0.0:
                raise ValueError("not-evaluable contribution must use a zero reliability score")
        elif self.reliability_band is not expected:
            raise ValueError("reliability band does not match reliability score")
        return self


class DisagreementRecord(FrozenModel):
    """A visible cross-source conflict that aggregation cannot erase."""

    disagreement_id: Identifier
    source_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=M2003_MAX_CONTRIBUTIONS)
    description: NonEmptyStr
    status: DisagreementStatus
    resolution: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2003_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2003_MAX_EVIDENCE)


class IntegratedEvidenceObject(FrozenModel):
    """Attributable integrated evidence with reliability and conflicts."""

    integrated_id: Identifier
    version: SemanticVersion
    aggregate_claim: NonEmptyStr
    contributions: tuple[SourceContribution, ...] = Field(
        min_length=1, max_length=M2003_MAX_CONTRIBUTIONS
    )
    disagreements: tuple[DisagreementRecord, ...] = Field(
        default=(), max_length=M2003_MAX_DISAGREEMENTS
    )
    aggregate_values: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M2003_MAX_AGGREGATES)
    configuration: AggregationConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2003_MAX_EVIDENCE)

    @model_validator(mode="after")
    def object_is_closed(self) -> IntegratedEvidenceObject:
        source_ids = tuple(item.source_id for item in self.contributions)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source contribution ids must be unique")
        allowed = set(source_ids)
        if any(not set(item.source_ids) <= allowed for item in self.disagreements):
            raise ValueError("disagreement references an unknown source")
        configuration = self.configuration
        if not configuration.component_specific or not configuration.preserve_source_identity:
            raise ValueError("configuration must preserve component-specific source identity")
        if not configuration.preserve_disagreement or not configuration.locked:
            raise ValueError("configuration must preserve disagreement and remain locked")
        return self


class FusionFinding(FrozenModel):
    finding_id: Identifier
    code: FusionFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2003_MAX_EVIDENCE)


class FuseProteinSubtypeEvidenceRequest(FrozenModel):
    """Provisional request bound to the M20-02 alignment result."""

    operation: Literal["fuse_protein_subtype_evidence"] = M2003_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2003_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    alignment_result: ArtifactReference
    contributions: tuple[SourceContribution, ...] = Field(
        min_length=1, max_length=M2003_MAX_CONTRIBUTIONS
    )
    disagreements: tuple[DisagreementRecord, ...] = Field(
        default=(), max_length=M2003_MAX_DISAGREEMENTS
    )
    aggregate_values: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M2003_MAX_AGGREGATES)
    configuration: AggregationConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2003_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> FuseProteinSubtypeEvidenceRequest:
        if self.alignment_result.media_type != M2003_M2002_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M20-02 alignment result")
        source_ids = tuple(item.source_id for item in self.contributions)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("request source contribution ids must be unique")
        allowed = set(source_ids)
        if any(not set(item.source_ids) <= allowed for item in self.disagreements):
            raise ValueError("request disagreement references an unknown source")
        artifact_ids = {item.artifact.artifact_id for item in self.contributions}
        declared_ids = {item.artifact_id for item in self.source_artifacts}
        if not artifact_ids <= declared_ids:
            raise ValueError("source artifacts must declare every contribution artifact")
        disagreement_ids = tuple(item.disagreement_id for item in self.disagreements)
        if len(disagreement_ids) != len(set(disagreement_ids)):
            raise ValueError("request disagreement ids must be unique")
        return self


class ProteinSubtypeIntegratedEvidenceResult(FrozenModel):
    """Integrated evidence result with explicit attribution and abstention."""

    output_type: Literal["protein_subtype_integrated_evidence"] = (
        "protein_subtype_integrated_evidence"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2003_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: FuseProteinSubtypeEvidenceRequest
    status: FusionStatus
    integrated_evidence: IntegratedEvidenceObject | None = None
    findings: tuple[FusionFinding, ...] = Field(default=(), max_length=M2003_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2003_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2003_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeIntegratedEvidenceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        has_unsafe_source = any(
            item.reliability_band is ReliabilityBand.NOT_EVALUABLE
            for item in self.request.contributions
        )
        if self.status is FusionStatus.INTEGRATED:
            if (
                self.integrated_evidence is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or has_unsafe_source
            ):
                raise ValueError("integrated result requires review-only attributable sources")
            integrated_evidence = self.integrated_evidence
            if integrated_evidence.contributions != self.request.contributions:
                raise ValueError("integrated result must preserve exact source contributions")
            if integrated_evidence.disagreements != self.request.disagreements:
                raise ValueError("integrated result must preserve exact disagreements")
            if integrated_evidence.aggregate_values != self.request.aggregate_values:
                raise ValueError("integrated result must preserve exact aggregate values")
            if integrated_evidence.configuration != self.request.configuration:
                raise ValueError("integrated result must preserve the locked configuration")
        elif (
            self.integrated_evidence is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no integrated object and safe status")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("result finding ids must be unique")
        requires_review = any(
            item.status is not DisagreementStatus.RESOLVED for item in self.request.disagreements
        )
        if requires_review and not self.human_review_required:
            raise ValueError("unresolved disagreement requires human review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2003_CONTRACT_VERSION",
    "M2003_DOSSIER_SHA256",
    "M2003_DOSSIER_SLICE",
    "M2003_EVIDENCE_CLAIM",
    "M2003_GATE",
    "M2003_M2002_INPUT_MEDIA_TYPE",
    "M2003_MAX_AGGREGATES",
    "M2003_MAX_CANONICAL_REQUEST_BYTES",
    "M2003_MAX_CANONICAL_RESULT_BYTES",
    "M2003_MAX_CONTRIBUTIONS",
    "M2003_MAX_DISAGREEMENTS",
    "M2003_MAX_EVIDENCE",
    "M2003_MAX_FINDINGS",
    "M2003_MODULE_ID",
    "M2003_OPERATION",
    "M2003_OUTPUT_MEDIA_TYPE",
    "M2003_OWNER",
    "M2003_PARENT",
    "M2003_PROVISIONAL_ABI",
    "M2003_SAFETY_CLASS",
    "AggregationConfiguration",
    "DisagreementRecord",
    "DisagreementStatus",
    "FuseProteinSubtypeEvidenceRequest",
    "FusionFinding",
    "FusionFindingCode",
    "FusionStatus",
    "IntegratedEvidenceObject",
    "ProteinSubtypeIntegratedEvidenceResult",
    "ReliabilityBand",
    "SourceContribution",
    "SourceKind",
]
