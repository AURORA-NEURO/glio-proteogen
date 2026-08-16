"""Provisional M20-02 cross-source alignment and reconciliation contracts.

The M20-02 dossier requires seven-dimensional alignment with explicit conflict
detection.  The ABI is provisional; unsupported or missing evidence abstains
and never becomes a negative finding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m20_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 6920-6960.
M2002_MODULE_ID: Final = "GLIO-PROTEOGEN-M20-02"
M2002_OPERATION: Final = "align_protein_subtype_sources"
M2002_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2002_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-02+json"
M2002_M2001_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-01+json"
M2002_PARENT: Final = "protein subtype"
M2002_OWNER: Final = "Quality engineering"
M2002_SAFETY_CLASS: Final = "S2"
M2002_GATE: Final = "G1"
M2002_PROVISIONAL_ABI: Final = True
M2002_MAX_OBSERVATIONS: Final = 256
M2002_MAX_DISCREPANCIES: Final = 128
M2002_MAX_DIMENSIONS: Final = 7
M2002_MAX_EVIDENCE: Final = 64
M2002_MAX_FINDINGS: Final = 64
M2002_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2002_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


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
    observation_id: Identifier
    dimension: AlignmentDimension
    source_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=64)
    reference_value: NonEmptyStr
    observed_values: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=64)
    status: AlignmentObservationStatus
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2002_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2002_MAX_EVIDENCE)

    @model_validator(mode="after")
    def source_ids_are_unique(self) -> DiscrepancyMapEntry:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("discrepancy source ids must be unique")
        return self


class AlignmentConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_dimensions: tuple[AlignmentDimension, ...] = Field(
        min_length=M2002_MAX_DIMENSIONS, max_length=M2002_MAX_DIMENSIONS
    )
    conflict_requires_review: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2002_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_dimensions_are_required(self) -> AlignmentConfiguration:
        if len(set(self.required_dimensions)) != M2002_MAX_DIMENSIONS:
            raise ValueError("alignment configuration dimensions must be unique")
        if set(self.required_dimensions) != set(AlignmentDimension):
            raise ValueError("alignment configuration must require all seven dimensions")
        return self


class AlignedEvidenceBundle(FrozenModel):
    bundle_id: Identifier
    version: SemanticVersion
    source_artifacts: tuple[ArtifactReference, ...] = Field(min_length=2, max_length=64)
    observations: tuple[AlignmentObservation, ...] = Field(
        min_length=1, max_length=M2002_MAX_OBSERVATIONS
    )
    discrepancies: tuple[DiscrepancyMapEntry, ...] = Field(
        default=(), max_length=M2002_MAX_DISCREPANCIES
    )
    configuration: AlignmentConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2002_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_is_closed(self) -> AlignedEvidenceBundle:
        observation_ids = tuple(item.observation_id for item in self.observations)
        discrepancy_ids = tuple(item.discrepancy_id for item in self.discrepancies)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("alignment observation ids must be unique")
        if len(discrepancy_ids) != len(set(discrepancy_ids)):
            raise ValueError("discrepancy ids must be unique")
        allowed = {artifact.artifact_id for artifact in self.source_artifacts}
        for item in self.observations:
            if not set(item.source_ids) <= allowed:
                raise ValueError("alignment entry references an unknown source artifact")
        for discrepancy in self.discrepancies:
            if not set(discrepancy.source_ids) <= allowed:
                raise ValueError("alignment entry references an unknown source artifact")
        observed_dimensions = {item.dimension for item in self.observations}
        if observed_dimensions != set(AlignmentDimension):
            raise ValueError("alignment bundle must cover all seven dimensions")
        if len(observed_dimensions) != len(self.observations):
            raise ValueError("alignment bundle must contain one observation per dimension")
        if any(
            discrepancy.resolution is None
            for discrepancy in self.discrepancies
            if discrepancy.severity is DiscrepancySeverity.CRITICAL
        ):
            raise ValueError("critical discrepancies require an explicit resolution")
        return self


class AlignmentFinding(FrozenModel):
    finding_id: Identifier
    code: AlignmentFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2002_MAX_EVIDENCE)


class AlignProteinSubtypeSourcesRequest(FrozenModel):
    """Provisional request bound to the M20-01 upstream resolver result."""

    operation: Literal["align_protein_subtype_sources"] = M2002_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2002_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    source_artifacts: tuple[ArtifactReference, ...] = Field(min_length=2, max_length=64)
    observations: tuple[AlignmentObservation, ...] = Field(
        min_length=1, max_length=M2002_MAX_OBSERVATIONS
    )
    discrepancies: tuple[DiscrepancyMapEntry, ...] = Field(
        default=(), max_length=M2002_MAX_DISCREPANCIES
    )
    configuration: AlignmentConfiguration
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> AlignProteinSubtypeSourcesRequest:
        if self.upstream_result.media_type != M2002_M2001_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M20-01 resolver result")
        source_ids = {artifact.artifact_id for artifact in self.source_artifacts}
        for item in self.observations:
            if not set(item.source_ids) <= source_ids:
                raise ValueError("alignment entry references an unknown source artifact")
        for discrepancy in self.discrepancies:
            if not set(discrepancy.source_ids) <= source_ids:
                raise ValueError("alignment entry references an unknown source artifact")
        return self


class ProteinSubtypeAlignmentResult(FrozenModel):
    """Aligned bundle and discrepancy map with safe abstention."""

    output_type: Literal["protein_subtype_alignment"] = "protein_subtype_alignment"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2002_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AlignProteinSubtypeSourcesRequest
    status: AlignmentStatus
    aligned_bundle: AlignedEvidenceBundle | None = None
    findings: tuple[AlignmentFinding, ...] = Field(default=(), max_length=M2002_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2002_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2002_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeAlignmentResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("alignment finding ids must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("alignment result evidence digests must be unique")
        if self.status is AlignmentStatus.ALIGNED:
            if (
                self.aligned_bundle is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.human_review_required
            ):
                raise ValueError("aligned result requires a supported evidence bundle")
            if any(
                item.status is not AlignmentObservationStatus.ALIGNED
                for item in self.aligned_bundle.observations
            ):
                raise ValueError("aligned result cannot contain conflicted observations")
            if any(item.resolution is None for item in self.aligned_bundle.discrepancies):
                raise ValueError("aligned result requires every discrepancy to be resolved")
        elif (
            self.aligned_bundle is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no bundle, safe status, and review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2002_CONTRACT_VERSION",
    "M2002_GATE",
    "M2002_M2001_INPUT_MEDIA_TYPE",
    "M2002_MAX_CANONICAL_REQUEST_BYTES",
    "M2002_MAX_CANONICAL_RESULT_BYTES",
    "M2002_MAX_DIMENSIONS",
    "M2002_MAX_DISCREPANCIES",
    "M2002_MAX_EVIDENCE",
    "M2002_MAX_FINDINGS",
    "M2002_MAX_OBSERVATIONS",
    "M2002_MODULE_ID",
    "M2002_OPERATION",
    "M2002_OUTPUT_MEDIA_TYPE",
    "M2002_OWNER",
    "M2002_PARENT",
    "M2002_PROVISIONAL_ABI",
    "M2002_SAFETY_CLASS",
    "AlignProteinSubtypeSourcesRequest",
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
    "ProteinSubtypeAlignmentResult",
]
