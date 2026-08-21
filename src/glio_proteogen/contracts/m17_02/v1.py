"""Provisional M17-02 cross-source alignment and reconciliation contracts.

The dossier requires alignment across sample, time, territory, analyte,
modality, reference, and biological context while keeping irreconcilable
conflicts explicit.  The ABI is not frozen; this contract emits only an
aligned evidence bundle and discrepancy map for the variant-peptide parent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m17_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 5840-5883.
M1702_MODULE_ID: Final = "GLIO-PROTEOGEN-M17-02"
M1702_OPERATION: Final = "align_variant_peptide_cross_source_evidence"
M1702_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1702_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m17-02+json"
M1702_PARENT: Final = "variant_peptide"
M1702_OWNER: Final = "Computational biology"
M1702_SAFETY_CLASS: Final = "S2"
M1702_GATE: Final = "G1"
M1702_PROVISIONAL_ABI: Final = True
M1702_MAX_OBSERVATIONS: Final = 256
M1702_MAX_DISCREPANCIES: Final = 128
M1702_MAX_EVIDENCE: Final = 64
M1702_MAX_AXES: Final = 8
M1702_MAX_FINDINGS: Final = 64
M1702_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1702_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1702_EVIDENCE_CLAIM: Final = (
    "Caller-declared M17-02 alignment, discrepancy, support and provenance material; "
    "issuer authority is not authenticated."
)


class AlignmentAxis(StrEnum):
    SAMPLE = "sample"
    TIME = "time"
    TERRITORY = "territory"
    ANALYTE = "analyte"
    MODALITY = "modality"
    REFERENCE = "reference"
    BIOLOGICAL_CONTEXT = "biological_context"


class SourceModality(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME = "genome"
    TRANSCRIPTOME = "transcriptome"
    PTM = "ptm"
    METABOLOME = "metabolome"
    LIPIDOME = "lipidome"


class AlignmentStatus(StrEnum):
    ALIGNED = "aligned"
    PARTIAL = "partial"
    CONFLICTED = "conflicted"
    UNRESOLVED = "unresolved"
    ABSTAINED = "abstained"


class AlignmentResultStatus(StrEnum):
    RECONCILED = "reconciled"
    ABSTAINED = "abstained"


_DISCREPANCY_AXIS: Final[dict[str, AlignmentAxis]] = {
    "sample_mismatch": AlignmentAxis.SAMPLE,
    "time_mismatch": AlignmentAxis.TIME,
    "territory_mismatch": AlignmentAxis.TERRITORY,
    "analyte_mismatch": AlignmentAxis.ANALYTE,
    "modality_mismatch": AlignmentAxis.MODALITY,
    "reference_mismatch": AlignmentAxis.REFERENCE,
    "biological_context_conflict": AlignmentAxis.BIOLOGICAL_CONTEXT,
    "unresolved_alignment": AlignmentAxis.SAMPLE,
}


class DiscrepancyCode(StrEnum):
    SAMPLE_MISMATCH = "sample_mismatch"
    TIME_MISMATCH = "time_mismatch"
    TERRITORY_MISMATCH = "territory_mismatch"
    ANALYTE_MISMATCH = "analyte_mismatch"
    MODALITY_MISMATCH = "modality_mismatch"
    REFERENCE_MISMATCH = "reference_mismatch"
    BIOLOGICAL_CONTEXT_CONFLICT = "biological_context_conflict"
    UNRESOLVED_ALIGNMENT = "unresolved_alignment"


class AlignmentFindingCode(StrEnum):
    DISCREPANCY_REQUIRES_REVIEW = "discrepancy_requires_review"
    REQUIRED_AXIS_MISSING = "required_axis_missing"
    IDENTITY_UNRESOLVED = "identity_unresolved"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class AlignmentConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    conflicts_preserved: Literal[True] = True
    unresolved_quarantined: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1702_MAX_EVIDENCE)


class AlignmentPolicy(FrozenModel):
    required_axes: tuple[AlignmentAxis, ...] = Field(min_length=1, max_length=M1702_MAX_AXES)
    conflict_preservation_required: Literal[True] = True
    quarantine_unresolved: Literal[True] = True
    configuration: AlignmentConfiguration

    @model_validator(mode="after")
    def required_axes_are_unique(self) -> AlignmentPolicy:
        if len(set(self.required_axes)) != len(self.required_axes):
            raise ValueError("required alignment axes must be unique")
        if set(self.required_axes) != set(AlignmentAxis):
            raise ValueError("alignment policy must declare all seven required axes")
        return self


class SourceObservation(FrozenModel):
    observation_id: Identifier
    modality: SourceModality
    sample_id: Identifier
    time_key: NonEmptyStr
    territory: NonEmptyStr
    analyte: NonEmptyStr
    reference: NonEmptyStr
    biological_context: NonEmptyStr
    source_artifact: ArtifactReference
    status: AlignmentStatus
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def aligned_observation_has_evidence(self) -> SourceObservation:
        if self.status is AlignmentStatus.ALIGNED and not self.evidence:
            raise ValueError("aligned source observation requires evidence")
        return self


class Discrepancy(FrozenModel):
    discrepancy_id: Identifier
    code: DiscrepancyCode
    axis: AlignmentAxis
    observation_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=M1702_MAX_OBSERVATIONS)
    message: NonEmptyStr
    review_required: bool = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def discrepancy_is_reviewable(self) -> Discrepancy:
        if not self.review_required:
            raise ValueError("discrepancies must remain reviewable")
        expected_axis = _DISCREPANCY_AXIS[self.code.value]
        if self.axis is not expected_axis:
            raise ValueError("discrepancy code must match its alignment axis")
        return self


class AlignedEvidenceBundle(FrozenModel):
    bundle_id: Identifier
    version: SemanticVersion
    observations: tuple[SourceObservation, ...] = Field(
        min_length=1, max_length=M1702_MAX_OBSERVATIONS
    )
    discrepancy_map: tuple[Discrepancy, ...] = Field(default=(), max_length=M1702_MAX_DISCREPANCIES)
    alignment_status: AlignmentStatus
    conflicts_preserved: Literal[True] = True
    immutable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def observation_ids_are_unique(self) -> AlignedEvidenceBundle:
        ids = tuple(item.observation_id for item in self.observations)
        if len(ids) != len(set(ids)):
            raise ValueError("aligned observation ids must be unique")
        discrepancy_ids = tuple(item.discrepancy_id for item in self.discrepancy_map)
        if len(discrepancy_ids) != len(set(discrepancy_ids)):
            raise ValueError("aligned discrepancy ids must be unique")
        observed = set(ids)
        if any(set(item.observation_ids) - observed for item in self.discrepancy_map):
            raise ValueError("discrepancy observations must belong to the aligned bundle")
        if self.alignment_status is AlignmentStatus.ALIGNED and self.discrepancy_map:
            raise ValueError("aligned bundle cannot hide discrepancies")
        if (
            self.alignment_status in {AlignmentStatus.CONFLICTED, AlignmentStatus.UNRESOLVED}
            and not self.discrepancy_map
        ):
            raise ValueError("conflicted bundle requires an explicit discrepancy map")
        return self


class AlignmentFinding(FrozenModel):
    finding_id: Identifier
    code: AlignmentFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1702_MAX_EVIDENCE)


class AlignVariantPeptideCrossSourceEvidenceRequest(FrozenModel):
    """Provisional request for cross-source alignment and reconciliation."""

    operation: Literal["align_variant_peptide_cross_source_evidence"] = M1702_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1702_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    observations: tuple[SourceObservation, ...] = Field(
        min_length=2, max_length=M1702_MAX_OBSERVATIONS
    )
    policy: AlignmentPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1702_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_observations_are_unique(self) -> AlignVariantPeptideCrossSourceEvidenceRequest:
        ids = tuple(item.observation_id for item in self.observations)
        if len(ids) != len(set(ids)):
            raise ValueError("request observation ids must be unique")
        return self


class VariantPeptideCrossSourceAlignmentResult(FrozenModel):
    """Aligned evidence bundle and discrepancy map with safe abstention."""

    output_type: Literal["variant_peptide_cross_source_alignment"] = (
        "variant_peptide_cross_source_alignment"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1702_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: AlignVariantPeptideCrossSourceEvidenceRequest
    status: AlignmentResultStatus
    aligned_bundle: AlignedEvidenceBundle | None = None
    discrepancy_map: tuple[Discrepancy, ...] = Field(default=(), max_length=M1702_MAX_DISCREPANCIES)
    findings: tuple[AlignmentFinding, ...] = Field(default=(), max_length=M1702_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant_peptide"] = M1702_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1702_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideCrossSourceAlignmentResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        discrepancy_ids = tuple(item.discrepancy_id for item in self.discrepancy_map)
        if len(discrepancy_ids) != len(set(discrepancy_ids)):
            raise ValueError("result discrepancy ids must be unique")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("alignment result requires evidence references")
        finding_codes = tuple(item.code for item in self.findings)
        if len(finding_codes) != len(set(finding_codes)):
            raise ValueError("alignment finding codes must be unique")
        if self.status is AlignmentResultStatus.RECONCILED:
            if (
                self.aligned_bundle is None
                or self.abstention_reason is not None
                or self.support_decision.status
                not in {SupportStatus.SUPPORTED, SupportStatus.REVIEW_REQUIRED}
                or self.human_review_required
                or self.aligned_bundle.alignment_status is not AlignmentStatus.ALIGNED
            ):
                raise ValueError("reconciled result requires a supported aligned bundle")
            if tuple(self.discrepancy_map) != tuple(self.aligned_bundle.discrepancy_map):
                raise ValueError("result discrepancy map must match aligned bundle")
        elif (
            self.aligned_bundle is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no bundle and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1702_CONTRACT_VERSION",
    "M1702_EVIDENCE_CLAIM",
    "M1702_GATE",
    "M1702_MAX_AXES",
    "M1702_MAX_CANONICAL_REQUEST_BYTES",
    "M1702_MAX_CANONICAL_RESULT_BYTES",
    "M1702_MAX_DISCREPANCIES",
    "M1702_MAX_EVIDENCE",
    "M1702_MAX_FINDINGS",
    "M1702_MAX_OBSERVATIONS",
    "M1702_MODULE_ID",
    "M1702_OPERATION",
    "M1702_OUTPUT_MEDIA_TYPE",
    "M1702_OWNER",
    "M1702_PARENT",
    "M1702_PROVISIONAL_ABI",
    "M1702_SAFETY_CLASS",
    "AlignVariantPeptideCrossSourceEvidenceRequest",
    "AlignedEvidenceBundle",
    "AlignmentAxis",
    "AlignmentConfiguration",
    "AlignmentFinding",
    "AlignmentFindingCode",
    "AlignmentPolicy",
    "AlignmentResultStatus",
    "AlignmentStatus",
    "Discrepancy",
    "DiscrepancyCode",
    "SourceModality",
    "SourceObservation",
    "VariantPeptideCrossSourceAlignmentResult",
]
