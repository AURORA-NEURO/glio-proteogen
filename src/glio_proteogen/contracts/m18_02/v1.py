"""Provisional M18-02 cross-source alignment contracts.

M18-02 owns sample, time, territory, analyte, modality, reference and
biological-context alignment beneath Spatial proteomics projection.  Conflicts
remain explicit in a discrepancy map; unsupported or missing evidence never
becomes a negative finding.  The public ABI is provisional pending
Bioinformatics owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m18_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M18-02 dossier slice.
M1802_MODULE_ID: Final = "GLIO-PROTEOGEN-M18-02"
M1802_OPERATION: Final = "align_biomarker_panel_sources"
M1802_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1802_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-02+json"
M1802_M1801_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-01+json"
M1802_PARENT: Final = "biomarker panel"
M1802_OWNER: Final = "Bioinformatics"
M1802_SAFETY_CLASS: Final = "S2"
M1802_GATE: Final = "G1"
M1802_PROVISIONAL_ABI: Final = True
M1802_MAX_OBSERVATIONS: Final = 256
M1802_MAX_DISCREPANCIES: Final = 128
M1802_MAX_DIMENSIONS: Final = 7
M1802_MAX_EVIDENCE: Final = 64
M1802_MAX_FINDINGS: Final = 64
M1802_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1802_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1802_EVIDENCE_CLAIM: Final = (
    "Caller-declared M18-02 alignment, source identity and discrepancy material; "
    "issuer authority is not authenticated."
)


class AlignmentDimension(StrEnum):
    SAMPLE = "sample"
    TIME = "time"
    TERRITORY = "territory"
    ANALYTE = "analyte"
    MODALITY = "modality"
    REFERENCE = "reference"
    BIOLOGICAL_CONTEXT = "biological_context"


class AlignmentObservationStatus(StrEnum):
    ALIGNED = "aligned"
    CONFLICTED = "conflicted"
    NOT_EVALUABLE = "not_evaluable"


class AlignmentStatus(StrEnum):
    ALIGNED = "aligned"
    ABSTAINED = "abstained"


class DiscrepancySeverity(StrEnum):
    CRITICAL = "critical"
    MATERIAL = "material"
    ROUTINE = "routine"


class AlignmentFindingCode(StrEnum):
    DIMENSION_CONFLICT = "dimension_conflict"
    INPUT_INCOMPLETE = "input_incomplete"
    IDENTITY_MISMATCH = "identity_mismatch"
    REFERENCE_MISMATCH = "reference_mismatch"
    DISCREPANCY_UNRESOLVED = "discrepancy_unresolved"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class AlignmentObservation(FrozenModel):
    """One dimension-level comparison across source artifacts."""

    observation_id: Identifier
    dimension: AlignmentDimension
    source_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=64)
    reference_value: NonEmptyStr
    observed_values: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=64)
    status: AlignmentObservationStatus
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def source_ids_are_unique(self) -> AlignmentObservation:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("alignment observation source ids must be unique")
        return self


class DiscrepancyMapEntry(FrozenModel):
    discrepancy_id: Identifier
    dimension: AlignmentDimension
    source_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=64)
    severity: DiscrepancySeverity
    description: NonEmptyStr
    resolution: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def resolution_is_safe(self) -> DiscrepancyMapEntry:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("discrepancy source ids must be unique")
        return self


class AlignmentConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_dimensions: tuple[AlignmentDimension, ...] = Field(
        min_length=M1802_MAX_DIMENSIONS, max_length=M1802_MAX_DIMENSIONS
    )
    conflict_requires_review: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_dimensions_are_required(self) -> AlignmentConfiguration:
        if set(self.required_dimensions) != set(AlignmentDimension):
            raise ValueError("alignment configuration must require all seven dimensions")
        return self


class AlignedEvidenceBundle(FrozenModel):
    """Aligned source bundle with explicit discrepancy map."""

    bundle_id: Identifier
    version: SemanticVersion
    source_artifacts: tuple[ArtifactReference, ...] = Field(min_length=2, max_length=64)
    observations: tuple[AlignmentObservation, ...] = Field(
        min_length=1, max_length=M1802_MAX_OBSERVATIONS
    )
    discrepancies: tuple[DiscrepancyMapEntry, ...] = Field(
        default=(), max_length=M1802_MAX_DISCREPANCIES
    )
    configuration: AlignmentConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1802_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> AlignedEvidenceBundle:
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        observation_ids = tuple(item.observation_id for item in self.observations)
        discrepancy_ids = tuple(item.discrepancy_id for item in self.discrepancies)
        dimensions = tuple(item.dimension for item in self.observations)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("aligned bundle source artifacts must be unique")
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("alignment observation ids must be unique")
        if len(discrepancy_ids) != len(set(discrepancy_ids)):
            raise ValueError("discrepancy ids must be unique")
        if len(dimensions) != len(set(dimensions)) or set(dimensions) != set(AlignmentDimension):
            raise ValueError("aligned bundle must cover all seven alignment dimensions")
        if any(
            item.status is AlignmentObservationStatus.ALIGNED
            and any(value != item.reference_value for value in item.observed_values)
            for item in self.observations
        ):
            raise ValueError("aligned observations must equal their reference value")
        if any(not set(item.source_ids) <= set(source_ids) for item in self.observations):
            raise ValueError("bundle entries reference unknown source artifacts")
        if any(not set(item.source_ids) <= set(source_ids) for item in self.discrepancies):
            raise ValueError("bundle entries reference unknown source artifacts")
        return self


class AlignmentFinding(FrozenModel):
    finding_id: Identifier
    code: AlignmentFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1802_MAX_EVIDENCE)


class AlignBiomarkerPanelSourcesRequest(FrozenModel):
    """Provisional request bound to the M18-01 upstream resolver result."""

    operation: Literal["align_biomarker_panel_sources"] = M1802_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1802_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    source_artifacts: tuple[ArtifactReference, ...] = Field(min_length=2, max_length=64)
    observations: tuple[AlignmentObservation, ...] = Field(
        min_length=1, max_length=M1802_MAX_OBSERVATIONS
    )
    discrepancies: tuple[DiscrepancyMapEntry, ...] = Field(
        default=(), max_length=M1802_MAX_DISCREPANCIES
    )
    configuration: AlignmentConfiguration
    support_decision: SupportDecision
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AlignBiomarkerPanelSourcesRequest:
        if self.upstream_result.media_type != M1802_M1801_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M18-01 resolver result")
        artifact_ids = tuple(artifact.artifact_id for artifact in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("request source artifacts must be unique")
        source_ids = set(artifact_ids)
        if self.upstream_result.artifact_id not in source_ids:
            raise ValueError("upstream result must be listed in source artifacts")
        if any(not set(item.source_ids) <= source_ids for item in self.observations):
            raise ValueError("observation references an unknown source artifact")
        if any(not set(item.source_ids) <= source_ids for item in self.discrepancies):
            raise ValueError("discrepancy references an unknown source artifact")
        observation_ids = tuple(item.observation_id for item in self.observations)
        discrepancy_ids = tuple(item.discrepancy_id for item in self.discrepancies)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("request observation ids must be unique")
        if len(discrepancy_ids) != len(set(discrepancy_ids)):
            raise ValueError("request discrepancy ids must be unique")
        return self


class BiomarkerPanelAlignmentResult(FrozenModel):
    """Aligned bundle and discrepancy map with safe abstention."""

    output_type: Literal["biomarker_panel_alignment"] = "biomarker_panel_alignment"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1802_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AlignBiomarkerPanelSourcesRequest
    status: AlignmentStatus
    aligned_bundle: AlignedEvidenceBundle | None = None
    findings: tuple[AlignmentFinding, ...] = Field(default=(), max_length=M1802_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M1802_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1802_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelAlignmentResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is AlignmentStatus.ALIGNED:
            if (
                self.aligned_bundle is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("aligned result requires a supported evidence bundle")
        elif (
            self.aligned_bundle is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no bundle and safe status")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        finding_codes = tuple(finding.code for finding in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("alignment finding ids must be unique")
        if len(finding_codes) != len(set(finding_codes)):
            raise ValueError("alignment finding codes must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1802_CONTRACT_VERSION",
    "M1802_EVIDENCE_CLAIM",
    "M1802_GATE",
    "M1802_M1801_INPUT_MEDIA_TYPE",
    "M1802_MAX_CANONICAL_REQUEST_BYTES",
    "M1802_MAX_CANONICAL_RESULT_BYTES",
    "M1802_MAX_DIMENSIONS",
    "M1802_MAX_DISCREPANCIES",
    "M1802_MAX_EVIDENCE",
    "M1802_MAX_FINDINGS",
    "M1802_MAX_OBSERVATIONS",
    "M1802_MODULE_ID",
    "M1802_OPERATION",
    "M1802_OUTPUT_MEDIA_TYPE",
    "M1802_OWNER",
    "M1802_PARENT",
    "M1802_PROVISIONAL_ABI",
    "M1802_SAFETY_CLASS",
    "AlignBiomarkerPanelSourcesRequest",
    "AlignedEvidenceBundle",
    "AlignmentConfiguration",
    "AlignmentDimension",
    "AlignmentFinding",
    "AlignmentFindingCode",
    "AlignmentObservation",
    "AlignmentObservationStatus",
    "AlignmentStatus",
    "BiomarkerPanelAlignmentResult",
    "DiscrepancyMapEntry",
    "DiscrepancySeverity",
]
