"""Provisional M16-02 cross-source alignment and reconciliation contracts.

The M16-02 dossier requires sample, time, territory, analyte, modality,
reference, and biological-context alignment with conflict detection. Locked
fixtures must reconcile correctly while irreconcilable conflicts stay explicit
and reviewable; unsupported cases abstain rather than becoming negatives.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m16_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M16-02 dossier slice.
M1602_MODULE_ID: Final = "GLIO-PROTEOGEN-M16-02"
M1602_OPERATION: Final = "reconcile_cross_source_alignment"
M1602_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1602_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-02+json"
M1602_M1601_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-01+json"
M1602_PARENT: Final = "protein_rna_discordance"
M1602_OWNER: Final = "Scientific engineering"
M1602_SAFETY_CLASS: Final = "S2"
M1602_GATE: Final = "G1"
M1602_PROVISIONAL_ABI: Final = True
M1602_MAX_LINKS: Final = 2_048
M1602_MAX_DISCREPANCIES: Final = 512
M1602_MAX_DIMENSIONS: Final = 7
M1602_MAX_OBSERVED_VALUES: Final = 128
M1602_MAX_EVIDENCE: Final = 64
M1602_MAX_DIAGNOSTICS: Final = 128
M1602_MAX_FINDINGS: Final = 64
M1602_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1602_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1602_EVIDENCE_CLAIM: Final = (
    "Caller-declared M16-02 alignment and discrepancy evidence; issuer authority "
    "is not authenticated."
)


class AlignmentDimension(StrEnum):
    SAMPLE = "sample"
    TIME = "time"
    TERRITORY = "territory"
    ANALYTE = "analyte"
    MODALITY = "modality"
    REFERENCE = "reference"
    BIOLOGICAL_CONTEXT = "biological_context"


class AlignmentLinkStatus(StrEnum):
    ALIGNED = "aligned"
    DISCREPANT = "discrepant"
    NOT_EVALUABLE = "not_evaluable"


class DiscrepancySeverity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


class DiscrepancyResolutionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    NOT_EVALUABLE = "not_evaluable"


class AlignmentDecisionStatus(StrEnum):
    RECONCILED = "reconciled"
    REVIEW_REQUIRED = "review_required"
    ABSTAINED = "abstained"


class AlignmentFindingCode(StrEnum):
    INPUT_INCOMPLETE = "input_incomplete"
    DISCREPANCY_OPEN = "discrepancy_open"
    CRITICAL_CONFLICT = "critical_conflict"
    REFERENCE_MISMATCH = "reference_mismatch"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class AlignmentLink(FrozenModel):
    """One typed alignment decision over immutable source artifacts."""

    link_id: Identifier
    dimensions: tuple[AlignmentDimension, ...] = Field(
        min_length=1, max_length=M1602_MAX_DIMENSIONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1602_MAX_EVIDENCE
    )
    canonical_key: NonEmptyStr
    observed_values: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1602_MAX_OBSERVED_VALUES
    )
    status: AlignmentLinkStatus
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1602_MAX_EVIDENCE)

    @model_validator(mode="after")
    def source_references_are_unique(self) -> AlignmentLink:
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("alignment source references must be unique")
        return self


class DiscrepancyRecord(FrozenModel):
    """Explicit discrepancy record; unresolved conflicts remain visible."""

    discrepancy_id: Identifier
    dimensions: tuple[AlignmentDimension, ...] = Field(
        min_length=1, max_length=M1602_MAX_DIMENSIONS
    )
    source_link_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1602_MAX_LINKS)
    description: NonEmptyStr
    severity: DiscrepancySeverity
    resolution_status: DiscrepancyResolutionStatus
    resolution: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1602_MAX_EVIDENCE)

    @model_validator(mode="after")
    def resolution_matches_status(self) -> DiscrepancyRecord:
        if self.resolution_status is DiscrepancyResolutionStatus.RESOLVED:
            if self.resolution is None:
                raise ValueError("resolved discrepancy requires a resolution")
        elif self.resolution is not None:
            raise ValueError("open discrepancy cannot claim a resolution")
        return self


class AlignmentConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    reference_artifact: ArtifactReference
    enabled_dimensions: tuple[AlignmentDimension, ...] = Field(
        min_length=1, max_length=M1602_MAX_DIMENSIONS
    )
    conflict_policy: NonEmptyStr
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1602_MAX_EVIDENCE)


class AlignedEvidenceBundle(FrozenModel):
    """Versioned aligned bundle with a closed, reviewable discrepancy map."""

    bundle_id: Identifier
    version: SemanticVersion
    links: tuple[AlignmentLink, ...] = Field(min_length=1, max_length=M1602_MAX_LINKS)
    discrepancies: tuple[DiscrepancyRecord, ...] = Field(
        default=(), max_length=M1602_MAX_DISCREPANCIES
    )
    configuration: AlignmentConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1602_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> AlignedEvidenceBundle:
        link_ids = tuple(item.link_id for item in self.links)
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("alignment link ids must be unique")
        discrepancy_ids = tuple(item.discrepancy_id for item in self.discrepancies)
        if len(discrepancy_ids) != len(set(discrepancy_ids)):
            raise ValueError("discrepancy ids must be unique")
        known_links = set(link_ids)
        for discrepancy in self.discrepancies:
            if not set(discrepancy.source_link_ids) <= known_links:
                raise ValueError("discrepancy references an unknown alignment link")
        if not set(self.configuration.enabled_dimensions) <= set(AlignmentDimension):
            raise ValueError("configuration contains an unsupported alignment dimension")
        return self


class AlignmentDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: AlignmentLinkStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1602_MAX_EVIDENCE)


class ReconcileCrossSourceAlignmentRequest(FrozenModel):
    """Provisional request bound to the M16-01 upstream object."""

    operation: Literal["reconcile_cross_source_alignment"] = M1602_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1602_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: AlignmentConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1602_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ReconcileCrossSourceAlignmentRequest:
        if self.upstream_result.media_type != M1602_M1601_INPUT_MEDIA_TYPE:
            raise ValueError("alignment request must bind the provisional M16-01 result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("request source artifact references must be unique")
        return self


class ProteinRnaDiscordanceAlignmentResult(FrozenModel):
    """Aligned bundle with explicit discrepancy review and abstention."""

    output_type: Literal["protein_rna_discordance_alignment"] = (
        "protein_rna_discordance_alignment"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1602_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ReconcileCrossSourceAlignmentRequest
    status: AlignmentDecisionStatus
    bundle: AlignedEvidenceBundle | None = None
    diagnostics: tuple[AlignmentDiagnostic, ...] = Field(
        min_length=1, max_length=M1602_MAX_DIAGNOSTICS
    )
    findings: tuple[AlignmentFindingCode, ...] = Field(
        default=(), max_length=M1602_MAX_FINDINGS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1602_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1602_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceAlignmentResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        critical_open = bool(
            self.bundle
            and any(
                item.severity is DiscrepancySeverity.CRITICAL
                and item.resolution_status is not DiscrepancyResolutionStatus.RESOLVED
                for item in self.bundle.discrepancies
            )
        )
        if self.status is AlignmentDecisionStatus.RECONCILED:
            if (
                self.bundle is None
                or critical_open
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("reconciled result requires supported conflict-free alignment")
        elif self.status is AlignmentDecisionStatus.REVIEW_REQUIRED:
            if (
                self.bundle is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
            ):
                raise ValueError("review result requires a bundle and explicit human review")
        elif (
            self.bundle is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no bundle and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1602_CONTRACT_VERSION",
    "M1602_EVIDENCE_CLAIM",
    "M1602_GATE",
    "M1602_M1601_INPUT_MEDIA_TYPE",
    "M1602_MAX_CANONICAL_REQUEST_BYTES",
    "M1602_MAX_CANONICAL_RESULT_BYTES",
    "M1602_MAX_DIAGNOSTICS",
    "M1602_MAX_DIMENSIONS",
    "M1602_MAX_DISCREPANCIES",
    "M1602_MAX_EVIDENCE",
    "M1602_MAX_FINDINGS",
    "M1602_MAX_LINKS",
    "M1602_MAX_OBSERVED_VALUES",
    "M1602_MODULE_ID",
    "M1602_OPERATION",
    "M1602_OUTPUT_MEDIA_TYPE",
    "M1602_OWNER",
    "M1602_PARENT",
    "M1602_PROVISIONAL_ABI",
    "M1602_SAFETY_CLASS",
    "AlignedEvidenceBundle",
    "AlignmentConfiguration",
    "AlignmentDecisionStatus",
    "AlignmentDiagnostic",
    "AlignmentDimension",
    "AlignmentFindingCode",
    "AlignmentLink",
    "AlignmentLinkStatus",
    "DiscrepancyRecord",
    "DiscrepancyResolutionStatus",
    "DiscrepancySeverity",
    "ProteinRnaDiscordanceAlignmentResult",
    "ReconcileCrossSourceAlignmentRequest",
]
