"""Provisional M19-02 cross-source alignment and reconciliation contracts.

The M19-02 dossier requires alignment across sample, time, territory, analyte,
modality, reference, and biological context with explicit conflict detection.
The ABI is provisional; unsupported or missing evidence abstains and never
becomes a negative finding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m19_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 6560-6600.
M1902_MODULE_ID: Final = "GLIO-PROTEOGEN-M19-02"
M1902_OPERATION: Final = "align_proteotype_sources"
M1902_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1902_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-02+json"
M1902_M1901_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-01+json"
M1902_PARENT: Final = "proteotype"
M1902_OWNER: Final = "ML engineering"
M1902_SAFETY_CLASS: Final = "S2"
M1902_GATE: Final = "G1"
M1902_PROVISIONAL_ABI: Final = True
M1902_MAX_OBSERVATIONS: Final = 256
M1902_MAX_DISCREPANCIES: Final = 128
M1902_MAX_DIMENSIONS: Final = 7
M1902_MAX_EVIDENCE: Final = 64
M1902_MAX_FINDINGS: Final = 64
M1902_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1902_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1902_EVIDENCE_CLAIM: Final = (
    "Caller-declared M19-02 alignment, source identity and discrepancy material; "
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1902_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def source_ids_are_unique(self) -> DiscrepancyMapEntry:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("discrepancy source ids must be unique")
        return self


class AlignmentConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_dimensions: tuple[AlignmentDimension, ...] = Field(
        min_length=M1902_MAX_DIMENSIONS, max_length=M1902_MAX_DIMENSIONS
    )
    conflict_requires_review: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1902_MAX_EVIDENCE)

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
        min_length=1, max_length=M1902_MAX_OBSERVATIONS
    )
    discrepancies: tuple[DiscrepancyMapEntry, ...] = Field(
        default=(), max_length=M1902_MAX_DISCREPANCIES
    )
    configuration: AlignmentConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1902_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> AlignedEvidenceBundle:
        observation_ids = tuple(item.observation_id for item in self.observations)
        discrepancy_ids = tuple(item.discrepancy_id for item in self.discrepancies)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("alignment observation ids must be unique")
        if len(discrepancy_ids) != len(set(discrepancy_ids)):
            raise ValueError("discrepancy ids must be unique")
        allowed = {artifact.artifact_id for artifact in self.source_artifacts}
        if any(not set(item.source_ids) <= allowed for item in self.observations):
            raise ValueError("observation references an unknown source artifact")
        if any(not set(item.source_ids) <= allowed for item in self.discrepancies):
            raise ValueError("discrepancy references an unknown source artifact")
        return self


class AlignmentFinding(FrozenModel):
    finding_id: Identifier
    code: AlignmentFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1902_MAX_EVIDENCE)


class AlignProteotypeSourcesRequest(FrozenModel):
    """Provisional request bound to the M19-01 upstream resolver result."""

    operation: Literal["align_proteotype_sources"] = M1902_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1902_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    source_artifacts: tuple[ArtifactReference, ...] = Field(min_length=2, max_length=64)
    observations: tuple[AlignmentObservation, ...] = Field(
        min_length=1, max_length=M1902_MAX_OBSERVATIONS
    )
    discrepancies: tuple[DiscrepancyMapEntry, ...] = Field(
        default=(), max_length=M1902_MAX_DISCREPANCIES
    )
    configuration: AlignmentConfiguration
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AlignProteotypeSourcesRequest:
        if self.upstream_result.media_type != M1902_M1901_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M19-01 resolver result")
        source_ids = {artifact.artifact_id for artifact in self.source_artifacts}
        if any(not set(item.source_ids) <= source_ids for item in self.observations):
            raise ValueError("observation references an unknown source artifact")
        if any(not set(item.source_ids) <= source_ids for item in self.discrepancies):
            raise ValueError("discrepancy references an unknown source artifact")
        return self


class ProteotypeAlignmentResult(FrozenModel):
    """Aligned bundle and discrepancy map with safe abstention."""

    output_type: Literal["proteotype_alignment"] = "proteotype_alignment"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1902_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AlignProteotypeSourcesRequest
    status: AlignmentStatus
    aligned_bundle: AlignedEvidenceBundle | None = None
    findings: tuple[AlignmentFinding, ...] = Field(default=(), max_length=M1902_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1902_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1902_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeAlignmentResult:
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
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1902_CONTRACT_VERSION",
    "M1902_EVIDENCE_CLAIM",
    "M1902_GATE",
    "M1902_M1901_INPUT_MEDIA_TYPE",
    "M1902_MAX_CANONICAL_REQUEST_BYTES",
    "M1902_MAX_CANONICAL_RESULT_BYTES",
    "M1902_MAX_DIMENSIONS",
    "M1902_MAX_DISCREPANCIES",
    "M1902_MAX_EVIDENCE",
    "M1902_MAX_FINDINGS",
    "M1902_MAX_OBSERVATIONS",
    "M1902_MODULE_ID",
    "M1902_OPERATION",
    "M1902_OUTPUT_MEDIA_TYPE",
    "M1902_OWNER",
    "M1902_PARENT",
    "M1902_PROVISIONAL_ABI",
    "M1902_SAFETY_CLASS",
    "AlignProteotypeSourcesRequest",
    "AlignedEvidenceBundle",
    "AlignmentConfiguration",
    "AlignmentDimension",
    "AlignmentFinding",
    "AlignmentFindingCode",
    "AlignmentObservation",
    "AlignmentObservationStatus",
    "AlignmentStatus",
    "DiscrepancyMapEntry",
    "DiscrepancySeverity",
    "ProteotypeAlignmentResult",
]
