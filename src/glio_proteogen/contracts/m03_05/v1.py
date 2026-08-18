"""Strict M03-05 protein-inference artifact and contamination contracts.

M03-05 consumes only a content-addressed projection of M03-04 and an opaque
evidence-unit ledger.  It never receives raw spectra, sequences, peptide strings,
protein accessions, or inferred biological identities.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m03_01 import (  # noqa: TC001 - Pydantic resolves models.
    ProteinInferenceApplicability,
    SearchSpaceComposition,
)
from glio_proteogen.contracts.m03_02 import ArtifactClaimRole
from glio_proteogen.contracts.m03_03 import (
    ProteinInferenceBuildState,
    ProteinInferenceRawFormat,
    ProteinInferenceRawRole,
)
from glio_proteogen.contracts.m03_04 import (
    M0304_MAX_SPECTRA_SOURCES,
    ProteinInferenceQualityDisposition,
    ProteinInferenceQualityMetricCode,
    ProteinInferenceQualityMetricDirection,
    ProteinInferenceQualityMetricStatus,
    ProteinInferenceQualityObservationState,
    ProteinInferenceQualityResult,
    ProteinInferenceRawQualityClaimReceipt,
    ProteinInferenceRawQualitySourceReceipt,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    IdentityLineageState,
    Limitation,
    NonEmptyStr,
    NonInferenceResultModel,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0305_MODULE_ID: Final = "GLIO-PROTEOGEN-M03-05"
M0305_OPERATION: Final = "detect_protein_inference_artifacts"
M0305_CONTRACT_VERSION: Final = "1.0.0"
M0305_PARENT: Final = "complex_activity"
M0305_OWNER: Final = "Data engineering"
M0305_SAFETY_CLASS: Final = "S2"
M0305_GATE: Final = "G1"
M0305_RATE_SCALE: Final = 1_000_000
M0305_MAX_SOURCES: Final = 64
M0305_MAX_CLAIMS: Final = 48
M0305_MAX_UPSTREAM_CLAIMS: Final = 256
M0305_UNIT_KIND_COUNT: Final = 6
M0305_SIGNAL_COUNT: Final = 8
M0305_MAX_UNITS: Final = 512
M0305_MAX_SIGNAL_SCORES: Final = M0305_MAX_UNITS * M0305_SIGNAL_COUNT
M0305_MAX_CONTAMINATION_FLAGS: Final = 3 * M0305_MAX_UNITS
M0305_MAX_UNIT_SOURCE_REFS: Final = 8
M0305_MAX_UNIT_CLAIM_REFS: Final = 8
M0305_MAX_COUNT: Final = 10_000_000
M0305_MAX_PROFILES: Final = 16
M0305_MAX_APPROVED_VERSIONS: Final = 32
# Seven controls + policy + active profile + eight thresholds + ledger.
M0305_MAX_EVIDENCE: Final = 18
# Five findings for each of three contamination signals and four findings for
# each of the remaining five signals: 3 * 5 + 5 * 4 = 35.
M0305_MAX_FINDINGS: Final = 35
M0305_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0305_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0305_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0305_DETECTOR_LIMITATION_CODE: Final = "protein_inference_artifact_mask_only"
M0305_SCORE_LIMITATION_CODE: Final = "evidence_score_not_calibrated_probability"
M0305_AUTHORITY_LIMITATION_CODE: Final = "quality_receipt_content_not_authenticated"
M0305_EVIDENCE_CLAIM: Final = (
    "Caller-declared content-addressed protein-inference artifact evidence."
)
M0305_SENSITIVITY_NOTES: Final = (
    "Missing, unsupported, and indeterminate signals remain explicitly typed.",
    "Evidence scores are deterministic integer evidence fractions, not probabilities.",
    "Signals outside a unit kind's locked domain remain not applicable.",
)
M0305_UNCERTAINTY_RATIONALES: Final = (
    "Measurement uncertainty is not estimated from the compact evidence ledger.",
    "Sampling uncertainty is not estimated by deterministic evidence scoring.",
    "The deterministic threshold evaluator fits no parameters.",
    "No calibrated classifier or protein-inference model is executed.",
    "Protein, proteoform, and kinase identity remain outside this detector.",
    "Support is a deterministic reviewed-threshold decision.",
    "Transportability requires external assay and contamination-panel validation.",
)
_OPAQUE_IDENTIFIER_PATTERN: Final = re.compile(r"^(source|claim|unit)\.[0-9a-f]{64}$")


class ProteinInferenceArtifactSignalCode(StrEnum):
    CONTAMINANT_REFERENCE_SUPPORT = "contaminant_reference_support"
    DECOY_COMPETITION_FAILURE = "decoy_competition_failure"
    LOW_COMPLEXITY_EVIDENCE = "low_complexity_evidence"
    NONUNIQUE_MAPPING = "nonunique_mapping"
    BATCH_INCONSISTENCY = "batch_inconsistency"
    BARCODE_INDEX_COLLISION = "barcode_index_collision"
    TECHNICAL_CARRYOVER = "technical_carryover"
    SAMPLE_CONTEXT_DISCORDANCE = "sample_context_discordance"


class ProteinInferenceEvidenceUnitKind(StrEnum):
    PEPTIDE_EVIDENCE = "peptide_evidence"
    PROTEIN_GROUP = "protein_group"
    AMBIGUITY_CLASS = "ambiguity_class"
    PROTEOFORM_CLAIM = "proteoform_claim"
    CONTROL_GROUP = "control_group"
    SAMPLE_CONTEXT_BINDING = "sample_context_binding"


class ProteinInferenceArtifactObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class ProteinInferenceArtifactFlagState(StrEnum):
    CLEAR = "clear"
    SUSPECTED = "suspected"
    DETECTED = "detected"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"


class ProteinInferenceArtifactPosteriorState(StrEnum):
    CLEAR = "clear"
    SUSPECTED = "suspected"
    DETECTED = "detected"
    INDETERMINATE = "indeterminate"


class ProteinInferenceArtifactDisposition(StrEnum):
    CLEARED = "cleared"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"
    REJECTED = "rejected"


class ProteinInferenceArtifactFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"
    REJECT = "reject"


class ProteinInferenceArtifactFindingCode(StrEnum):
    UPSTREAM_REJECTED = "upstream_rejected"
    UPSTREAM_QUARANTINED = "upstream_quarantined"
    UPSTREAM_ABSTAINED = "upstream_abstained"
    UPSTREAM_REVIEW_REQUIRED = "upstream_review_required"
    UPSTREAM_SHAPE_UNSUPPORTED = "upstream_shape_unsupported"
    EVIDENCE_LEDGER_BINDING_MISMATCH = "evidence_ledger_binding_mismatch"
    DETECTOR_PROFILE_UNSUPPORTED = "detector_profile_unsupported"
    REQUIRED_SIGNAL_MISSING = "required_signal_missing"
    REQUIRED_SIGNAL_UNSUPPORTED = "required_signal_unsupported"
    SIGNAL_NOT_EVALUABLE = "signal_not_evaluable"
    ARTIFACT_SUSPECTED = "artifact_suspected"
    ARTIFACT_DETECTED = "artifact_detected"
    CONTAMINATION_FLAGGED = "contamination_flagged"
    EVIDENCE_UNIT_BINDING_CONFLICT = "evidence_unit_binding_conflict"


_ACTION_BY_FINDING_CODE: Final = {
    ProteinInferenceArtifactFindingCode.UPSTREAM_REJECTED: (
        ProteinInferenceArtifactFindingAction.REJECT
    ),
    ProteinInferenceArtifactFindingCode.UPSTREAM_QUARANTINED: (
        ProteinInferenceArtifactFindingAction.QUARANTINE
    ),
    ProteinInferenceArtifactFindingCode.UPSTREAM_ABSTAINED: (
        ProteinInferenceArtifactFindingAction.ABSTAIN
    ),
    ProteinInferenceArtifactFindingCode.UPSTREAM_REVIEW_REQUIRED: (
        ProteinInferenceArtifactFindingAction.QUARANTINE
    ),
    ProteinInferenceArtifactFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        ProteinInferenceArtifactFindingAction.ABSTAIN
    ),
    ProteinInferenceArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH: (
        ProteinInferenceArtifactFindingAction.QUARANTINE
    ),
    ProteinInferenceArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED: (
        ProteinInferenceArtifactFindingAction.ABSTAIN
    ),
    ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_MISSING: (
        ProteinInferenceArtifactFindingAction.ABSTAIN
    ),
    ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_UNSUPPORTED: (
        ProteinInferenceArtifactFindingAction.ABSTAIN
    ),
    ProteinInferenceArtifactFindingCode.SIGNAL_NOT_EVALUABLE: (
        ProteinInferenceArtifactFindingAction.ABSTAIN
    ),
    ProteinInferenceArtifactFindingCode.ARTIFACT_SUSPECTED: (
        ProteinInferenceArtifactFindingAction.QUARANTINE
    ),
    ProteinInferenceArtifactFindingCode.ARTIFACT_DETECTED: (
        ProteinInferenceArtifactFindingAction.QUARANTINE
    ),
    ProteinInferenceArtifactFindingCode.CONTAMINATION_FLAGGED: (
        ProteinInferenceArtifactFindingAction.QUARANTINE
    ),
    ProteinInferenceArtifactFindingCode.EVIDENCE_UNIT_BINDING_CONFLICT: (
        ProteinInferenceArtifactFindingAction.QUARANTINE
    ),
}

_MESSAGE_BY_FINDING_CODE: Final = {
    ProteinInferenceArtifactFindingCode.UPSTREAM_REJECTED: (
        "M03-04 rejected the protein-inference quality result."
    ),
    ProteinInferenceArtifactFindingCode.UPSTREAM_QUARANTINED: (
        "M03-04 quarantined the protein-inference quality result."
    ),
    ProteinInferenceArtifactFindingCode.UPSTREAM_ABSTAINED: (
        "M03-04 abstained from protein-inference quality qualification."
    ),
    ProteinInferenceArtifactFindingCode.UPSTREAM_REVIEW_REQUIRED: (
        "M03-04 retained a qualified result that still requires governed review."
    ),
    ProteinInferenceArtifactFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        "The compact quality graph exceeds the reviewed M03-05 compute envelope."
    ),
    ProteinInferenceArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH: (
        "The artifact evidence ledger does not bind the exact compact quality receipt."
    ),
    ProteinInferenceArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED: (
        "No reviewed artifact profile applies to the declared assay metadata."
    ),
    ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_MISSING: (
        "A required artifact signal is missing."
    ),
    ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_UNSUPPORTED: (
        "A required artifact signal is unsupported."
    ),
    ProteinInferenceArtifactFindingCode.SIGNAL_NOT_EVALUABLE: (
        "An applicable artifact signal has no evaluable evidence units."
    ),
    ProteinInferenceArtifactFindingCode.ARTIFACT_SUSPECTED: (
        "Artifact evidence reached the reviewed suspicion threshold."
    ),
    ProteinInferenceArtifactFindingCode.ARTIFACT_DETECTED: (
        "Artifact evidence reached the reviewed exclusion threshold."
    ),
    ProteinInferenceArtifactFindingCode.CONTAMINATION_FLAGGED: (
        "Applicable contamination evidence was suspected or detected."
    ),
    ProteinInferenceArtifactFindingCode.EVIDENCE_UNIT_BINDING_CONFLICT: (
        "An evidence unit cites an absent or role-incompatible source or claim."
    ),
}


M0305_SIGNAL_APPLICABLE_UNIT_KINDS: Final[
    Mapping[ProteinInferenceArtifactSignalCode, frozenset[ProteinInferenceEvidenceUnitKind]]
] = MappingProxyType(
    {
        ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT: frozenset(
            {
                ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
                ProteinInferenceEvidenceUnitKind.PROTEOFORM_CLAIM,
                ProteinInferenceEvidenceUnitKind.CONTROL_GROUP,
            }
        ),
        ProteinInferenceArtifactSignalCode.DECOY_COMPETITION_FAILURE: frozenset(
            {
                ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
                ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS,
                ProteinInferenceEvidenceUnitKind.PROTEOFORM_CLAIM,
            }
        ),
        ProteinInferenceArtifactSignalCode.LOW_COMPLEXITY_EVIDENCE: frozenset(
            {
                ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
                ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS,
                ProteinInferenceEvidenceUnitKind.PROTEOFORM_CLAIM,
            }
        ),
        ProteinInferenceArtifactSignalCode.NONUNIQUE_MAPPING: frozenset(
            {
                ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
                ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS,
                ProteinInferenceEvidenceUnitKind.PROTEOFORM_CLAIM,
            }
        ),
        ProteinInferenceArtifactSignalCode.BATCH_INCONSISTENCY: frozenset(
            ProteinInferenceEvidenceUnitKind
        ),
        ProteinInferenceArtifactSignalCode.BARCODE_INDEX_COLLISION: frozenset(
            {
                ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
                ProteinInferenceEvidenceUnitKind.CONTROL_GROUP,
            }
        ),
        ProteinInferenceArtifactSignalCode.TECHNICAL_CARRYOVER: frozenset(
            {
                ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
                ProteinInferenceEvidenceUnitKind.CONTROL_GROUP,
            }
        ),
        ProteinInferenceArtifactSignalCode.SAMPLE_CONTEXT_DISCORDANCE: frozenset(
            {
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
                ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS,
                ProteinInferenceEvidenceUnitKind.PROTEOFORM_CLAIM,
                ProteinInferenceEvidenceUnitKind.SAMPLE_CONTEXT_BINDING,
            }
        ),
    }
)

M0305_CONTAMINATION_SIGNALS: Final = frozenset(
    {
        ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT,
        ProteinInferenceArtifactSignalCode.BARCODE_INDEX_COLLISION,
        ProteinInferenceArtifactSignalCode.TECHNICAL_CARRYOVER,
    }
)

M0305_SOURCE_ROLES_BY_UNIT_KIND: Final[
    Mapping[ProteinInferenceEvidenceUnitKind, frozenset[ProteinInferenceRawRole]]
] = MappingProxyType(
    {
        ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE: frozenset(
            {
                ProteinInferenceRawRole.SPECTRA,
                ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
                ProteinInferenceRawRole.CANONICAL_SEQUENCES,
                ProteinInferenceRawRole.DECOY_SEQUENCES,
                ProteinInferenceRawRole.ISOFORM_SEQUENCES,
                ProteinInferenceRawRole.VARIANT_SEQUENCES,
                ProteinInferenceRawRole.CONTAMINANT_SEQUENCES,
                ProteinInferenceRawRole.PTM_VOCABULARY,
            }
        ),
        ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP: frozenset(
            {
                ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
                ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
                ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
                ProteinInferenceRawRole.CANONICAL_SEQUENCES,
                ProteinInferenceRawRole.DECOY_SEQUENCES,
                ProteinInferenceRawRole.ISOFORM_SEQUENCES,
                ProteinInferenceRawRole.VARIANT_SEQUENCES,
                ProteinInferenceRawRole.CONTAMINANT_SEQUENCES,
            }
        ),
        ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS: frozenset(
            {
                ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
                ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
                ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
            }
        ),
        ProteinInferenceEvidenceUnitKind.PROTEOFORM_CLAIM: frozenset(
            {
                ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
                ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
                ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
                ProteinInferenceRawRole.ISOFORM_SEQUENCES,
                ProteinInferenceRawRole.VARIANT_SEQUENCES,
                ProteinInferenceRawRole.PTM_VOCABULARY,
            }
        ),
        ProteinInferenceEvidenceUnitKind.CONTROL_GROUP: frozenset(
            {
                ProteinInferenceRawRole.SPECTRA,
                ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
                ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
                ProteinInferenceRawRole.CONTAMINANT_SEQUENCES,
            }
        ),
        ProteinInferenceEvidenceUnitKind.SAMPLE_CONTEXT_BINDING: frozenset(
            {
                ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
                ProteinInferenceRawRole.GENOMIC_CONTEXT,
                ProteinInferenceRawRole.TRANSCRIPT_CONTEXT,
            }
        ),
    }
)

M0305_CLAIM_ROLES_BY_UNIT_KIND: Final[
    Mapping[ProteinInferenceEvidenceUnitKind, frozenset[ArtifactClaimRole]]
] = MappingProxyType(
    {
        ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE: frozenset(
            {ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST}
        ),
        ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP: frozenset(
            {
                ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST,
                ArtifactClaimRole.PROTEIN_GROUP_MANIFEST,
            }
        ),
        ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS: frozenset(
            {
                ArtifactClaimRole.PROTEIN_GROUP_MANIFEST,
                ArtifactClaimRole.AMBIGUITY_MANIFEST,
            }
        ),
        ProteinInferenceEvidenceUnitKind.PROTEOFORM_CLAIM: frozenset(
            {
                ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST,
                ArtifactClaimRole.PROTEIN_GROUP_MANIFEST,
                ArtifactClaimRole.AMBIGUITY_MANIFEST,
            }
        ),
        ProteinInferenceEvidenceUnitKind.CONTROL_GROUP: frozenset(
            {
                ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST,
                ArtifactClaimRole.PROTEIN_GROUP_MANIFEST,
            }
        ),
        ProteinInferenceEvidenceUnitKind.SAMPLE_CONTEXT_BINDING: frozenset(
            {ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE}
        ),
    }
)

_RAW_ROLE_BY_CLAIM_ROLE: Final = {
    ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST: ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
    ArtifactClaimRole.PROTEIN_GROUP_MANIFEST: ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
    ArtifactClaimRole.AMBIGUITY_MANIFEST: ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
    ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE: (
        ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE
    ),
}

_QUALITY_DIRECTION_BY_METRIC: Final = {
    ProteinInferenceQualityMetricCode.ADMITTED_SOURCE_COMPLETENESS: (
        ProteinInferenceQualityMetricDirection.AT_LEAST
    ),
    ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE: (
        ProteinInferenceQualityMetricDirection.AT_LEAST
    ),
    ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN: (
        ProteinInferenceQualityMetricDirection.AT_MOST
    ),
    ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE: (
        ProteinInferenceQualityMetricDirection.AT_LEAST
    ),
    ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT: (
        ProteinInferenceQualityMetricDirection.AT_LEAST
    ),
    ProteinInferenceQualityMetricCode.PROTEIN_GROUP_COMPETITION_CLOSURE: (
        ProteinInferenceQualityMetricDirection.AT_LEAST
    ),
    ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY: (
        ProteinInferenceQualityMetricDirection.AT_LEAST
    ),
    ProteinInferenceQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE: (
        ProteinInferenceQualityMetricDirection.AT_LEAST
    ),
}

_RAW_FORMAT_BY_ROLE: Final = {
    ProteinInferenceRawRole.SPECTRA: ProteinInferenceRawFormat.MZML,
    ProteinInferenceRawRole.PEPTIDE_EVIDENCE: ProteinInferenceRawFormat.MZIDENTML,
    ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST: (ProteinInferenceRawFormat.PROTEIN_GROUP_JSON),
    ProteinInferenceRawRole.AMBIGUITY_MANIFEST: ProteinInferenceRawFormat.AMBIGUITY_JSON,
    ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE: (
        ProteinInferenceRawFormat.COMPLEX_BUNDLE_JSON
    ),
    ProteinInferenceRawRole.CANONICAL_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.DECOY_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.ISOFORM_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.VARIANT_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.CONTAMINANT_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.PTM_VOCABULARY: ProteinInferenceRawFormat.PSI_MOD_OBO,
    ProteinInferenceRawRole.GENOMIC_CONTEXT: ProteinInferenceRawFormat.VCF,
    ProteinInferenceRawRole.TRANSCRIPT_CONTEXT: ProteinInferenceRawFormat.GFF3,
}


def _opaque_identifier(value: Identifier, prefix: str, label: str) -> Identifier:
    if not value.startswith(prefix) or _OPAQUE_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a content-derived opaque {prefix} identifier")
    return value


def _opaque_projection_id(prefix: Literal["source", "claim"], value: object) -> Identifier:
    return f"{prefix}.{sha256_digest(value).removeprefix('sha256:')}"


class ProteinInferenceArtifactThreshold(FrozenModel):
    signal_code: ProteinInferenceArtifactSignalCode
    review_threshold_ppm: int = Field(ge=0, le=M0305_RATE_SCALE)
    exclude_threshold_ppm: int = Field(ge=0, le=M0305_RATE_SCALE)
    required: bool
    applicable_unit_kinds: tuple[ProteinInferenceEvidenceUnitKind, ...] = Field(
        min_length=1,
        max_length=M0305_UNIT_KIND_COUNT,
    )
    evidence: ArtifactReference

    @field_validator("applicable_unit_kinds")
    @classmethod
    def applicable_kinds_are_canonical(
        cls,
        values: tuple[ProteinInferenceEvidenceUnitKind, ...],
    ) -> tuple[ProteinInferenceEvidenceUnitKind, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def threshold_is_locked(self) -> ProteinInferenceArtifactThreshold:
        if self.review_threshold_ppm > self.exclude_threshold_ppm:
            raise ValueError("artifact review threshold cannot exceed exclusion threshold")
        if len(self.applicable_unit_kinds) != len(set(self.applicable_unit_kinds)):
            raise ValueError("artifact threshold unit kinds must be unique")
        if set(self.applicable_unit_kinds) != set(
            M0305_SIGNAL_APPLICABLE_UNIT_KINDS[self.signal_code]
        ):
            raise ValueError("artifact threshold cannot redefine the locked signal domain")
        return self


class ProteinInferenceArtifactProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    applicability: ProteinInferenceApplicability
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0305_MAX_APPROVED_VERSIONS
    )
    approved_controlled_vocabulary_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0305_MAX_APPROVED_VERSIONS
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0305_MAX_APPROVED_VERSIONS
    )
    thresholds: tuple[ProteinInferenceArtifactThreshold, ...] = Field(
        min_length=M0305_SIGNAL_COUNT,
        max_length=M0305_SIGNAL_COUNT,
    )
    evidence: ArtifactReference

    @field_validator(
        "approved_assay_protocol_versions",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
    )
    @classmethod
    def approved_versions_are_canonical(
        cls,
        values: tuple[SemanticVersion, ...],
    ) -> tuple[SemanticVersion, ...]:
        return tuple(sorted(values))

    @field_validator("thresholds")
    @classmethod
    def thresholds_are_canonical(
        cls,
        values: tuple[ProteinInferenceArtifactThreshold, ...],
    ) -> tuple[ProteinInferenceArtifactThreshold, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def profile_is_closed(self) -> ProteinInferenceArtifactProfile:
        domains = (
            self.approved_assay_protocol_versions,
            self.approved_controlled_vocabulary_versions,
            self.approved_unit_system_versions,
        )
        if any(len(values) != len(set(values)) for values in domains):
            raise ValueError("approved artifact profile versions must be unique")
        codes = tuple(item.signal_code for item in self.thresholds)
        if len(codes) != len(set(codes)) or set(codes) != set(ProteinInferenceArtifactSignalCode):
            raise ValueError("artifact profile requires each of eight signals exactly once")
        return self


class ProteinInferenceArtifactPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_units: int = Field(gt=0, le=M0305_MAX_UNITS)
    max_sources: int = Field(gt=0, le=M0305_MAX_SOURCES)
    max_claims: int = Field(gt=0, le=M0305_MAX_CLAIMS)
    profiles: tuple[ProteinInferenceArtifactProfile, ...] = Field(
        min_length=1,
        max_length=M0305_MAX_PROFILES,
    )
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("profiles")
    @classmethod
    def profiles_are_canonical(
        cls,
        values: tuple[ProteinInferenceArtifactProfile, ...],
    ) -> tuple[ProteinInferenceArtifactProfile, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def policy_profiles_are_unambiguous(self) -> ProteinInferenceArtifactPolicy:
        identities = tuple((item.profile_id, item.version) for item in self.profiles)
        if len(identities) != len(set(identities)):
            raise ValueError("artifact policy profile identities must be unique")
        for index, left in enumerate(self.profiles):
            for right in self.profiles[index + 1 :]:
                overlaps = (
                    left.applicability is right.applicability
                    and bool(
                        set(left.approved_assay_protocol_versions)
                        & set(right.approved_assay_protocol_versions)
                    )
                    and bool(
                        set(left.approved_controlled_vocabulary_versions)
                        & set(right.approved_controlled_vocabulary_versions)
                    )
                    and bool(
                        set(left.approved_unit_system_versions)
                        & set(right.approved_unit_system_versions)
                    )
                )
                if overlaps:
                    raise ValueError("artifact profile match domains must be pairwise disjoint")
        return self


class ProteinInferenceArtifactQualityMetricReceipt(FrozenModel):
    metric_code: ProteinInferenceQualityMetricCode
    observation_state: ProteinInferenceQualityObservationState
    status: ProteinInferenceQualityMetricStatus
    required: bool
    direction: ProteinInferenceQualityMetricDirection
    pass_threshold_ppm: int = Field(ge=0, le=M0305_RATE_SCALE)
    warning_threshold_ppm: int = Field(ge=0, le=M0305_RATE_SCALE)
    numerator: int | None = Field(default=None, ge=0, le=M0305_MAX_COUNT)
    denominator: int | None = Field(default=None, ge=0, le=M0305_MAX_COUNT)
    value_ppm: int | None = Field(default=None, ge=0, le=M0305_RATE_SCALE)
    censored_count: int = Field(default=0, ge=0, le=M0305_MAX_COUNT)
    provenance_digest: Sha256Digest

    @model_validator(mode="after")
    def metric_shape_is_self_consistent(  # noqa: PLR0912 - explicit metric closure.
        self,
    ) -> ProteinInferenceArtifactQualityMetricReceipt:
        if self.direction is not _QUALITY_DIRECTION_BY_METRIC[self.metric_code]:
            raise ValueError("compact quality direction contradicts its metric")
        if (
            self.direction is ProteinInferenceQualityMetricDirection.AT_LEAST
            and self.warning_threshold_ppm > self.pass_threshold_ppm
        ) or (
            self.direction is ProteinInferenceQualityMetricDirection.AT_MOST
            and self.warning_threshold_ppm < self.pass_threshold_ppm
        ):
            raise ValueError("compact quality thresholds are directionally invalid")
        no_value_states = {
            ProteinInferenceQualityObservationState.MISSING,
            ProteinInferenceQualityObservationState.NOT_APPLICABLE,
            ProteinInferenceQualityObservationState.UNSUPPORTED,
        }
        if self.observation_state in no_value_states:
            if any(item is not None for item in (self.numerator, self.denominator, self.value_ppm)):
                raise ValueError("non-observed compact quality metrics cannot carry a ratio")
            expected = (
                ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
                if self.observation_state is ProteinInferenceQualityObservationState.NOT_APPLICABLE
                else ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
            )
            if self.status is not expected or self.censored_count != 0:
                raise ValueError("non-observed compact quality metric has an invalid status")
            return self
        if self.numerator is None or self.denominator is None:
            raise ValueError("observed compact quality metrics require a ratio")
        if self.numerator > self.denominator or self.censored_count > self.denominator:
            raise ValueError("compact quality counts contradict their denominator")
        if self.denominator == 0:
            if (
                self.numerator != 0
                or self.value_ppm is not None
                or self.status is not ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
            ):
                raise ValueError("zero-denominator compact metric must remain not evaluable")
        else:
            expected_value = (
                self.numerator * M0305_RATE_SCALE + self.denominator // 2
            ) // self.denominator
            if self.value_ppm != expected_value or self.status in {
                ProteinInferenceQualityMetricStatus.NOT_EVALUABLE,
                ProteinInferenceQualityMetricStatus.NOT_APPLICABLE,
            }:
                raise ValueError("compact quality value does not match its exact integer ratio")
            value_product = self.numerator * M0305_RATE_SCALE
            pass_product = self.pass_threshold_ppm * self.denominator
            warning_product = self.warning_threshold_ppm * self.denominator
            if self.direction is ProteinInferenceQualityMetricDirection.AT_LEAST:
                expected_status = (
                    ProteinInferenceQualityMetricStatus.PASS
                    if value_product >= pass_product
                    else ProteinInferenceQualityMetricStatus.WARNING
                    if value_product >= warning_product
                    else ProteinInferenceQualityMetricStatus.FAIL
                )
            else:
                expected_status = (
                    ProteinInferenceQualityMetricStatus.PASS
                    if value_product <= pass_product
                    else ProteinInferenceQualityMetricStatus.WARNING
                    if value_product <= warning_product
                    else ProteinInferenceQualityMetricStatus.FAIL
                )
            if self.status is not expected_status:
                raise ValueError("compact quality status contradicts its reviewed threshold")
        if (self.observation_state is ProteinInferenceQualityObservationState.CENSORED) != (
            self.censored_count > 0
        ):
            raise ValueError("compact censored state requires a positive censored count")
        return self


class ProteinInferenceArtifactQualityReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = M0305_CONTRACT_VERSION
    quality_result_digest: Sha256Digest
    quality_request_digest: Sha256Digest
    quality_policy_digest: Sha256Digest
    quality_configuration_digest: Sha256Digest
    quality_disposition: ProteinInferenceQualityDisposition
    quality_support_status: SupportStatus
    quality_human_review_required: bool
    quality_completed_at: AwareDatetime
    raw_quality_receipt_digest: Sha256Digest
    fact_ledger_digest: Sha256Digest | None = None
    quality_profile_digest: Sha256Digest | None = None
    admission_result_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    search_space_digest: Sha256Digest
    search_space_composition: SearchSpaceComposition
    identity_resolution_digest: Sha256Digest
    source_manifest_digest: Sha256Digest
    assay_protocol_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    applicability: ProteinInferenceApplicability | None = None
    controls_applicable: bool
    source_count: int = Field(ge=0, le=M0305_MAX_SOURCES)
    claim_count: int = Field(ge=0, le=M0305_MAX_UPSTREAM_CLAIMS)
    sources: tuple[ProteinInferenceRawQualitySourceReceipt, ...] = Field(
        default=(), max_length=M0305_MAX_SOURCES
    )
    claims: tuple[ProteinInferenceRawQualityClaimReceipt, ...] = Field(
        default=(), max_length=M0305_MAX_CLAIMS
    )
    quality_metrics: tuple[ProteinInferenceArtifactQualityMetricReceipt, ...] = Field(
        default=(), max_length=M0305_SIGNAL_COUNT
    )
    source_binding_digest: Sha256Digest
    claim_binding_digest: Sha256Digest
    quality_metric_binding_digest: Sha256Digest
    receipt_digest: Sha256Digest

    @field_validator("sources", "claims", "quality_metrics")
    @classmethod
    def projections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_is_closed(  # noqa: PLR0912 - explicit upstream envelope closure.
        self,
    ) -> ProteinInferenceArtifactQualityReceipt:
        from glio_proteogen.contracts.m03_05.canonical import (  # noqa: PLC0415
            artifact_quality_receipt_digest,
            claim_binding_digest,
            quality_metric_binding_digest,
            source_binding_digest,
        )

        identifiers = (
            tuple(item.source_id for item in self.sources),
            tuple(item.claim_id for item in self.claims),
            tuple(item.metric_code for item in self.quality_metrics),
        )
        if any(len(values) != len(set(values)) for values in identifiers):
            raise ValueError("artifact quality receipt projections must be unique")
        for source in self.sources:
            _opaque_identifier(source.source_id, "source.", "projected source identifier")
            if source.bound_claim_id is not None:
                _opaque_identifier(
                    source.bound_claim_id,
                    "claim.",
                    "projected bound-claim identifier",
                )
        for claim in self.claims:
            _opaque_identifier(claim.claim_id, "claim.", "projected claim identifier")
        traversable = self.quality_disposition is ProteinInferenceQualityDisposition.QUALIFIED
        if traversable:
            if (
                self.applicability is None
                or self.fact_ledger_digest is None
                or self.quality_profile_digest is None
                or len(self.sources) != self.source_count
                or len(self.claims) != self.claim_count
                or {item.metric_code for item in self.quality_metrics}
                != set(ProteinInferenceQualityMetricCode)
            ):
                raise ValueError("qualified quality receipt requires its exact compact graph")
            _validate_compact_quality_receipt_graph(self)
            optional_warning = False
            for metric in self.quality_metrics:
                allowed_control_na = (
                    metric.metric_code is ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY
                    and not self.controls_applicable
                    and metric.status is ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
                    and metric.observation_state
                    is ProteinInferenceQualityObservationState.NOT_APPLICABLE
                )
                if metric.status is ProteinInferenceQualityMetricStatus.FAIL or (
                    metric.required
                    and metric.status is not ProteinInferenceQualityMetricStatus.PASS
                    and not allowed_control_na
                ):
                    raise ValueError(
                        "qualified quality receipt contradicts its required metric status"
                    )
                optional_warning = optional_warning or (
                    not metric.required
                    and metric.status is ProteinInferenceQualityMetricStatus.WARNING
                )
            expected_qualified_support = (
                SupportStatus.LIMITED if optional_warning else SupportStatus.SUPPORTED
            )
            if self.quality_support_status is not expected_qualified_support:
                raise ValueError(
                    "qualified quality support status contradicts its optional metric warnings"
                )
        elif self.sources or self.claims or self.quality_metrics:
            raise ValueError("non-qualified quality receipt cannot expose graph projections")
        expected_support = {
            ProteinInferenceQualityDisposition.QUALIFIED: {
                SupportStatus.SUPPORTED,
                SupportStatus.LIMITED,
            },
            ProteinInferenceQualityDisposition.QUARANTINED: {SupportStatus.REVIEW_REQUIRED},
            ProteinInferenceQualityDisposition.ABSTAINED: {SupportStatus.UNSUPPORTED},
            ProteinInferenceQualityDisposition.REJECTED: {SupportStatus.UNSUPPORTED},
        }[self.quality_disposition]
        if self.quality_support_status not in expected_support:
            raise ValueError("quality receipt disposition and support status contradict")
        expected_review = (
            self.quality_disposition is not ProteinInferenceQualityDisposition.QUALIFIED
            or self.quality_support_status is SupportStatus.LIMITED
        )
        if self.quality_human_review_required != expected_review:
            raise ValueError("quality receipt disposition and review requirement contradict")
        if (
            self.source_binding_digest != source_binding_digest(self.sources)
            or self.claim_binding_digest != claim_binding_digest(self.claims)
            or self.quality_metric_binding_digest
            != quality_metric_binding_digest(self.quality_metrics)
            or self.receipt_digest != artifact_quality_receipt_digest(self)
        ):
            raise ValueError("artifact quality receipt digest closure failed")
        return self


def _validate_compact_quality_receipt_graph(
    receipt: ProteinInferenceArtifactQualityReceipt,
) -> None:
    roles = tuple(item.role for item in receipt.sources)
    role_counts = {role: roles.count(role) for role in ProteinInferenceRawRole}
    if not 1 <= role_counts[ProteinInferenceRawRole.SPECTRA] <= M0304_MAX_SPECTRA_SOURCES:
        raise ValueError("compact quality receipt requires bounded spectra sources")
    exact_source_roles = {
        ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
        ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
        ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
        ProteinInferenceRawRole.CANONICAL_SEQUENCES,
        ProteinInferenceRawRole.DECOY_SEQUENCES,
        ProteinInferenceRawRole.PTM_VOCABULARY,
    }
    if any(role_counts[role] != 1 for role in exact_source_roles):
        raise ValueError("compact quality receipt required roles must occur exactly once")
    claim_roles = tuple(item.claim_role for item in receipt.claims)
    peptide_claim_count = claim_roles.count(ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST)
    if peptide_claim_count < 1 or (
        role_counts[ProteinInferenceRawRole.PEPTIDE_EVIDENCE] != peptide_claim_count
    ):
        raise ValueError("compact peptide sources and claims must close exactly")
    if (
        claim_roles.count(ArtifactClaimRole.PROTEIN_GROUP_MANIFEST) != 1
        or claim_roles.count(ArtifactClaimRole.AMBIGUITY_MANIFEST) != 1
        or claim_roles.count(ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE) != 1
    ):
        raise ValueError("compact quality claims contradict the exact lineage role shape")
    composition = receipt.search_space_composition
    conditional = (
        (ProteinInferenceRawRole.ISOFORM_SEQUENCES, composition.isoform_sequences),
        (ProteinInferenceRawRole.VARIANT_SEQUENCES, composition.variant_sequences),
        (ProteinInferenceRawRole.CONTAMINANT_SEQUENCES, composition.contaminant_sequences),
    )
    if any(role_counts[role] != int(count > 0) for role, count in conditional):
        raise ValueError("compact conditional sources contradict the search-space composition")
    for role, required_count in (
        (ProteinInferenceRawRole.GENOMIC_CONTEXT, composition.variant_sequences),
        (ProteinInferenceRawRole.TRANSCRIPT_CONTEXT, composition.isoform_sequences),
    ):
        count = role_counts[role]
        if count > 1 or (required_count > 0 and count != 1):
            raise ValueError("compact context sources contradict the governed search space")
    claim_ids = {item.claim_id for item in receipt.claims}
    bound_ids = {item.bound_claim_id for item in receipt.sources if item.bound_claim_id is not None}
    if bound_ids != claim_ids:
        raise ValueError("compact source and claim identifiers do not form an exact cover")
    claims_by_id = {item.claim_id: item for item in receipt.claims}
    for source in receipt.sources:
        if (
            source.artifact_digest != source.source_digest
            or source.detected_format is not _RAW_FORMAT_BY_ROLE[source.role]
            or source.compression is None
            or source.diagnostic_codes
            or source.build.state
            not in {ProteinInferenceBuildState.EXACT, ProteinInferenceBuildState.NOT_APPLICABLE}
        ):
            raise ValueError("compact source projection is not a validated exact admission")
        if source.bound_claim_id is None:
            continue
        claim = claims_by_id[source.bound_claim_id]
        if (
            source.role is not _RAW_ROLE_BY_CLAIM_ROLE[claim.claim_role]
            or source.artifact_digest != claim.artifact_digest
        ):
            raise ValueError("compact source contradicts its bound lineage claim")


class ProteinInferenceArtifactSignal(FrozenModel):
    signal_code: ProteinInferenceArtifactSignalCode
    observation_state: ProteinInferenceArtifactObservationState
    supporting_count: int = Field(ge=0, le=M0305_MAX_COUNT)
    evaluated_count: int = Field(ge=0, le=M0305_MAX_COUNT)

    @model_validator(mode="after")
    def observation_is_closed(self) -> ProteinInferenceArtifactSignal:
        if self.observation_state is ProteinInferenceArtifactObservationState.OBSERVED:
            if self.supporting_count > self.evaluated_count:
                raise ValueError("artifact support count cannot exceed evaluated count")
        elif self.supporting_count != 0 or self.evaluated_count != 0:
            raise ValueError("non-observed artifact signals must carry zero counts")
        return self


class ProteinInferenceArtifactEvidenceUnit(FrozenModel):
    unit_id: Identifier
    unit_kind: ProteinInferenceEvidenceUnitKind
    source_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0305_MAX_UNIT_SOURCE_REFS)
    claim_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0305_MAX_UNIT_CLAIM_REFS)
    signals: tuple[ProteinInferenceArtifactSignal, ...] = Field(
        min_length=M0305_SIGNAL_COUNT,
        max_length=M0305_SIGNAL_COUNT,
    )

    @field_validator("unit_id")
    @classmethod
    def unit_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "unit.", "evidence-unit identifier")

    @field_validator("source_ids")
    @classmethod
    def source_identifiers_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        for value in values:
            _opaque_identifier(value, "source.", "unit source identifier")
        return tuple(sorted(values))

    @field_validator("claim_ids")
    @classmethod
    def claim_identifiers_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        for value in values:
            _opaque_identifier(value, "claim.", "unit claim identifier")
        return tuple(sorted(values))

    @field_validator("signals")
    @classmethod
    def signals_are_canonical(
        cls,
        values: tuple[ProteinInferenceArtifactSignal, ...],
    ) -> tuple[ProteinInferenceArtifactSignal, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def unit_is_closed(self) -> ProteinInferenceArtifactEvidenceUnit:
        if len(self.source_ids) != len(set(self.source_ids)) or len(self.claim_ids) != len(
            set(self.claim_ids)
        ):
            raise ValueError("artifact unit bindings must be unique")
        codes = tuple(item.signal_code for item in self.signals)
        if len(codes) != len(set(codes)) or set(codes) != set(ProteinInferenceArtifactSignalCode):
            raise ValueError("every artifact unit requires all eight exact signals")
        for signal in self.signals:
            applicable = self.unit_kind in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[signal.signal_code]
            if not applicable and not (
                signal.observation_state is ProteinInferenceArtifactObservationState.NOT_APPLICABLE
                and signal.supporting_count == 0
                and signal.evaluated_count == 0
            ):
                raise ValueError("out-of-domain artifact signals must be not applicable")
            if applicable and signal.observation_state is (
                ProteinInferenceArtifactObservationState.NOT_APPLICABLE
            ):
                raise ValueError("applicable artifact signals cannot be marked not applicable")
        return self


class ProteinInferenceArtifactEvidenceLedger(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    quality_result_digest: Sha256Digest
    admission_result_digest: Sha256Digest
    source_manifest_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    claim_binding_digest: Sha256Digest
    quality_metric_binding_digest: Sha256Digest
    applicability: ProteinInferenceApplicability
    units: tuple[ProteinInferenceArtifactEvidenceUnit, ...] = Field(
        min_length=1,
        max_length=M0305_MAX_UNITS,
    )
    evidence: ArtifactReference
    recorded_at: AwareDatetime
    ledger_digest: Sha256Digest

    @field_validator("units")
    @classmethod
    def units_are_canonical(
        cls,
        values: tuple[ProteinInferenceArtifactEvidenceUnit, ...],
    ) -> tuple[ProteinInferenceArtifactEvidenceUnit, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def ledger_is_content_addressed(self) -> ProteinInferenceArtifactEvidenceLedger:
        from glio_proteogen.contracts.m03_05.canonical import (  # noqa: PLC0415
            artifact_evidence_ledger_digest,
        )

        identifiers = tuple(item.unit_id for item in self.units)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("artifact evidence unit identifiers must be unique")
        if self.ledger_digest != artifact_evidence_ledger_digest(self):
            raise ValueError("artifact evidence-ledger digest does not match its content")
        return self


class DetectProteinInferenceArtifactsRequest(FrozenModel):
    operation: Literal["detect_protein_inference_artifacts"] = M0305_OPERATION
    contract_version: Literal["1.0.0"] = M0305_CONTRACT_VERSION
    context: ExecutionContext
    quality_receipt: ProteinInferenceArtifactQualityReceipt
    evidence_ledger: ProteinInferenceArtifactEvidenceLedger | None = None
    policy: ProteinInferenceArtifactPolicy
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_and_closed(self) -> DetectProteinInferenceArtifactsRequest:
        _require_authorized_context(self.context)
        receipt = self.quality_receipt
        ledger = self.evidence_ledger
        if max(receipt.quality_completed_at, self.policy.reviewed_at) > (self.context.occurred_at):
            raise ValueError("M03-05 inputs cannot postdate artifact detection")
        if self.context.references.identity_lineage.binding_digest != (
            receipt.identity_resolution_digest
        ):
            raise ValueError("identity control does not bind the compact quality receipt")
        if self.context.references.quality.evidence.digest != receipt.quality_result_digest:
            raise ValueError("quality control does not bind the compact M03-04 result")
        from glio_proteogen.contracts.m03_05.canonical import (  # noqa: PLC0415
            configuration_digest,
        )

        if self.context.references.approved_configuration.evidence.digest != (
            configuration_digest(self.policy)
        ):
            raise ValueError("approved configuration does not bind the artifact policy")
        supported_shape = (
            receipt.quality_disposition is ProteinInferenceQualityDisposition.QUALIFIED
            and receipt.source_count <= self.policy.max_sources
            and receipt.claim_count <= self.policy.max_claims
        )
        if supported_shape != (ledger is not None):
            raise ValueError("artifact ledger presence contradicts the traversal envelope")
        if ledger is not None and not (
            receipt.quality_completed_at <= ledger.recorded_at <= self.context.occurred_at
        ):
            raise ValueError("artifact facts must follow quality and precede detection")
        _validate_artifact_reference_consistency(self)
        if len(canonical_json_bytes(self.model_dump(mode="python"))) > (
            M0305_MAX_CANONICAL_REQUEST_BYTES
        ):
            raise ValueError("canonical M03-05 request exceeds its ingress ceiling")
        return self


class ProteinInferenceArtifactSignalProvenance(FrozenModel):
    quality_result_digest: Sha256Digest
    evidence_ledger_digest: Sha256Digest
    profile_digest: Sha256Digest
    threshold_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    claim_binding_digest: Sha256Digest
    quality_metric_binding_digest: Sha256Digest


class ProteinInferenceArtifactUnitProvenance(FrozenModel):
    quality_result_digest: Sha256Digest
    evidence_ledger_digest: Sha256Digest
    profile_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    claim_binding_digest: Sha256Digest
    quality_metric_binding_digest: Sha256Digest


class ProteinInferenceArtifactSignalScore(FrozenModel):
    unit_id: Identifier
    unit_kind: ProteinInferenceEvidenceUnitKind
    signal_code: ProteinInferenceArtifactSignalCode
    observation_state: ProteinInferenceArtifactObservationState
    flag_state: ProteinInferenceArtifactFlagState
    supporting_count: int | None = Field(default=None, ge=0, le=M0305_MAX_COUNT)
    evaluated_count: int | None = Field(default=None, ge=0, le=M0305_MAX_COUNT)
    evidence_score_ppm: int | None = Field(default=None, ge=0, le=M0305_RATE_SCALE)
    score_is_calibrated_probability: Literal[False] = False
    required: bool
    provenance: ProteinInferenceArtifactSignalProvenance

    @model_validator(mode="after")
    def score_shape_is_exact(self) -> ProteinInferenceArtifactSignalScore:
        if self.observation_state is ProteinInferenceArtifactObservationState.OBSERVED:
            if self.supporting_count is None or self.evaluated_count is None:
                raise ValueError("observed artifact signals require exact counts")
            if self.supporting_count > self.evaluated_count:
                raise ValueError("artifact support count cannot exceed evaluated count")
            if self.evaluated_count == 0:
                if (
                    self.supporting_count != 0
                    or self.evidence_score_ppm is not None
                    or self.flag_state is not ProteinInferenceArtifactFlagState.INDETERMINATE
                ):
                    raise ValueError("zero-denominator artifact evidence is indeterminate")
            else:
                expected_score = (
                    self.supporting_count * M0305_RATE_SCALE + self.evaluated_count // 2
                ) // self.evaluated_count
                if self.evidence_score_ppm != expected_score or self.flag_state in {
                    ProteinInferenceArtifactFlagState.INDETERMINATE,
                    ProteinInferenceArtifactFlagState.NOT_APPLICABLE,
                }:
                    raise ValueError("artifact evidence score contradicts its exact counts")
            return self
        if any(
            item is not None
            for item in (
                self.supporting_count,
                self.evaluated_count,
                self.evidence_score_ppm,
            )
        ):
            raise ValueError("non-observed artifact scores cannot carry counts or values")
        expected_flag = (
            ProteinInferenceArtifactFlagState.NOT_APPLICABLE
            if self.observation_state is ProteinInferenceArtifactObservationState.NOT_APPLICABLE
            else ProteinInferenceArtifactFlagState.INDETERMINATE
        )
        if self.flag_state is not expected_flag:
            raise ValueError("non-observed artifact score has an invalid flag state")
        return self


class ProteinInferenceArtifactPosterior(FrozenModel):
    unit_id: Identifier
    state: ProteinInferenceArtifactPosteriorState
    max_evidence_score_ppm: int | None = Field(default=None, ge=0, le=M0305_RATE_SCALE)
    score_is_calibrated_probability: Literal[False] = False
    contributing_signal_codes: tuple[ProteinInferenceArtifactSignalCode, ...] = Field(
        default=(), max_length=M0305_SIGNAL_COUNT
    )
    provenance: ProteinInferenceArtifactUnitProvenance

    @field_validator("contributing_signal_codes")
    @classmethod
    def contributing_signals_are_unique(
        cls,
        values: tuple[ProteinInferenceArtifactSignalCode, ...],
    ) -> tuple[ProteinInferenceArtifactSignalCode, ...]:
        if len(values) != len(set(values)):
            raise ValueError("artifact posterior contributing signals must be unique")
        return tuple(sorted(values))


class ProteinInferenceContaminationFlag(FrozenModel):
    unit_id: Identifier
    signal_code: ProteinInferenceArtifactSignalCode
    state: Literal[
        ProteinInferenceArtifactFlagState.SUSPECTED,
        ProteinInferenceArtifactFlagState.DETECTED,
    ]
    evidence_score_ppm: int = Field(ge=0, le=M0305_RATE_SCALE)
    score_is_calibrated_probability: Literal[False] = False
    provenance: ProteinInferenceArtifactSignalProvenance

    @model_validator(mode="after")
    def contamination_signal_is_closed(self) -> ProteinInferenceContaminationFlag:
        if self.signal_code not in M0305_CONTAMINATION_SIGNALS:
            raise ValueError("contamination flags require a locked contamination signal")
        return self


class ProteinInferenceEvidenceExclusionMask(FrozenModel):
    retain_unit_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0305_MAX_UNITS)
    review_unit_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0305_MAX_UNITS)
    exclude_unit_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0305_MAX_UNITS)

    @field_validator("retain_unit_ids", "review_unit_ids", "exclude_unit_ids")
    @classmethod
    def mask_identifiers_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def mask_partitions_are_disjoint(self) -> ProteinInferenceEvidenceExclusionMask:
        partitions = (
            self.retain_unit_ids,
            self.review_unit_ids,
            self.exclude_unit_ids,
        )
        if any(len(values) != len(set(values)) for values in partitions):
            raise ValueError("artifact mask partitions require unique unit identifiers")
        overlaps = any(
            set(left) & set(right)
            for index, left in enumerate(partitions)
            for right in partitions[index + 1 :]
        )
        if overlaps:
            raise ValueError("artifact mask partitions must be disjoint")
        return self


class ProteinInferenceArtifactFinding(FrozenModel):
    finding_id: Identifier
    code: ProteinInferenceArtifactFindingCode
    action: ProteinInferenceArtifactFindingAction
    signal_codes: tuple[ProteinInferenceArtifactSignalCode, ...] = Field(
        default=(), max_length=M0305_SIGNAL_COUNT
    )
    unit_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0305_MAX_UNITS)
    message: NonEmptyStr

    @field_validator("signal_codes")
    @classmethod
    def finding_signals_are_canonical(
        cls,
        values: tuple[ProteinInferenceArtifactSignalCode, ...],
    ) -> tuple[ProteinInferenceArtifactSignalCode, ...]:
        return tuple(sorted(values))

    @field_validator("unit_ids")
    @classmethod
    def finding_units_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def finding_is_closed(self) -> ProteinInferenceArtifactFinding:
        if len(self.signal_codes) != len(set(self.signal_codes)) or len(self.unit_ids) != len(
            set(self.unit_ids)
        ):
            raise ValueError("artifact finding references must be unique")
        expected = finding_for(
            self.code,
            signal_codes=self.signal_codes,
            unit_ids=self.unit_ids,
        )
        if self != expected:
            raise ValueError("M03-05 finding contradicts its closed vocabulary")
        return self


class ProteinInferenceArtifactComputationReceipt(FrozenModel):
    artifact_quality_receipt_digest: Sha256Digest
    evidence_ledger_digest: Sha256Digest | None = None
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    profile_digest: Sha256Digest | None = None
    supersedes_result_digest: Sha256Digest | None = None
    parent_target: Literal["complex_activity"] = M0305_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    disposition: ProteinInferenceArtifactDisposition


class ProteinInferenceArtifactDetectionResult(NonInferenceResultModel):
    output_type: Literal["protein_inference_artifact_mask"] = "protein_inference_artifact_mask"
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0305_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: DetectProteinInferenceArtifactsRequest
    receipt: ProteinInferenceArtifactComputationReceipt
    signal_scores: tuple[ProteinInferenceArtifactSignalScore, ...] = Field(
        default=(), max_length=M0305_MAX_SIGNAL_SCORES
    )
    artifact_posteriors: tuple[ProteinInferenceArtifactPosterior, ...] = Field(
        default=(), max_length=M0305_MAX_UNITS
    )
    contamination_flags: tuple[ProteinInferenceContaminationFlag, ...] = Field(
        default=(), max_length=M0305_MAX_CONTAMINATION_FLAGS
    )
    exclusion_mask: ProteinInferenceEvidenceExclusionMask
    findings: tuple[ProteinInferenceArtifactFinding, ...] = Field(
        default=(), max_length=M0305_MAX_FINDINGS
    )
    disposition: ProteinInferenceArtifactDisposition
    parent_target: Literal["complex_activity"] = M0305_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0305_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator(
        "signal_scores",
        "artifact_posteriors",
        "contamination_flags",
        "findings",
        "evidence",
        "limitations",
    )
    @classmethod
    def collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("uncertainty")
    @classmethod
    def uncertainty_notes_are_canonical(
        cls,
        value: UncertaintyProfile,
    ) -> UncertaintyProfile:
        return value.model_copy(
            update={"sensitivity_notes": tuple(sorted(value.sensitivity_notes))}
        )

    @field_validator("provenance")
    @classmethod
    def provenance_collections_are_canonical(
        cls,
        value: ProvenanceRecord,
    ) -> ProvenanceRecord:
        return value.model_copy(
            update={
                "input_digests": tuple(sorted(value.input_digests)),
                "control_decisions": tuple(
                    sorted(value.control_decisions, key=canonical_json_bytes)
                ),
            }
        )

    @model_validator(mode="after")
    def result_is_relationally_closed(  # noqa: PLR0912 - explicit replay closure.
        self,
    ) -> ProteinInferenceArtifactDetectionResult:
        from glio_proteogen.contracts.m03_05.canonical import (  # noqa: PLC0415
            canonical_request_digest,
            configuration_digest,
            normalized_request,
            policy_digest,
            result_payload_digest,
        )

        canonical_request = DetectProteinInferenceArtifactsRequest.model_validate_json(
            canonical_json_bytes(normalized_request(self.request)),
            strict=True,
        )
        if self.request != canonical_request:
            raise ValueError("M03-05 embedded request is not in canonical semantic order")

        scores = expected_signal_scores(self.request)
        posteriors = expected_artifact_posteriors(scores)
        flags = expected_contamination_flags(scores)
        mask = expected_exclusion_mask(posteriors)
        findings = expected_artifact_findings(self.request, scores, flags)
        disposition = expected_disposition(self.request, scores, findings)
        if not _semantic_tuple_equal(self.signal_scores, scores):
            raise ValueError("M03-05 signal scores do not replay from the evidence ledger")
        if not _semantic_tuple_equal(self.artifact_posteriors, posteriors):
            raise ValueError("M03-05 artifact posteriors do not replay from signal scores")
        if not _semantic_tuple_equal(self.contamination_flags, flags):
            raise ValueError("M03-05 contamination flags do not replay from signal scores")
        if self.exclusion_mask != mask:
            raise ValueError("M03-05 exclusion mask does not replay from artifact posteriors")
        if not _semantic_tuple_equal(self.findings, findings):
            raise ValueError("M03-05 findings do not replay from request and signal scores")
        request_hash = canonical_request_digest(self.request)
        policy_hash = policy_digest(self.request.policy)
        configuration_hash = configuration_digest(self.request.policy)
        if (
            self.result_id != f"result.m0305.{request_hash.removeprefix('sha256:')}"
            or self.request_digest != request_hash
            or self.policy_digest != policy_hash
            or self.configuration_digest != configuration_hash
            or self.receipt != expected_computation_receipt(self.request, disposition)
            or self.disposition is not disposition
        ):
            raise ValueError("M03-05 output envelope contradicts its replayed request")
        if self.completed_at != self.request.context.occurred_at:
            raise ValueError("M03-05 completion time must equal execution time")
        if self.support != expected_support(disposition):
            raise ValueError("M03-05 support is not deterministic")
        if not _uncertainty_equal(self.uncertainty, expected_uncertainty(disposition)):
            raise ValueError("M03-05 uncertainty is not deterministic")
        if not _provenance_equal(
            self.provenance,
            expected_provenance(self.request, disposition),
        ):
            raise ValueError("M03-05 provenance does not close")
        if not _semantic_tuple_equal(self.evidence, artifact_evidence_index(self.request)):
            raise ValueError("M03-05 evidence index does not close")
        if not _semantic_tuple_equal(self.limitations, expected_limitations()):
            raise ValueError("M03-05 limitations do not close")
        if self.human_review_required != (
            disposition is not ProteinInferenceArtifactDisposition.CLEARED
        ):
            raise ValueError("M03-05 human-review flag contradicts disposition")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("M03-05 result digest does not match its payload")
        return self


def _semantic_tuple_equal(left: tuple[object, ...], right: tuple[object, ...]) -> bool:
    return tuple(sorted(left, key=canonical_json_bytes)) == tuple(
        sorted(right, key=canonical_json_bytes)
    )


def _uncertainty_equal(left: UncertaintyProfile, right: UncertaintyProfile) -> bool:
    left_value = left.model_dump(mode="python", exclude_none=False)
    right_value = right.model_dump(mode="python", exclude_none=False)
    left_value["sensitivity_notes"] = tuple(sorted(left.sensitivity_notes))
    right_value["sensitivity_notes"] = tuple(sorted(right.sensitivity_notes))
    return canonical_json_bytes(left_value) == canonical_json_bytes(right_value)


def _provenance_equal(left: ProvenanceRecord, right: ProvenanceRecord) -> bool:
    left_value = left.model_dump(mode="python", exclude_none=False)
    right_value = right.model_dump(mode="python", exclude_none=False)
    for value in (left_value, right_value):
        value["input_digests"] = tuple(sorted(value["input_digests"]))
        value["control_decisions"] = tuple(
            sorted(value["control_decisions"], key=canonical_json_bytes)
        )
    return canonical_json_bytes(left_value) == canonical_json_bytes(right_value)


def artifact_quality_receipt(value: object) -> ProteinInferenceArtifactQualityReceipt:
    """Project a fully validated genuine M03-04 result into the M03-05 boundary."""

    result = ProteinInferenceQualityResult.model_validate(value, strict=True)
    raw = result.request.raw_quality_receipt
    traversable = result.disposition is ProteinInferenceQualityDisposition.QUALIFIED
    claim_aliases = {
        item.claim_id: _opaque_projection_id(
            "claim",
            {
                "claim_id": item.claim_id,
                "claim_role": item.claim_role,
                "artifact_digest": item.artifact_digest,
                "lineage_path_digest": item.lineage_path_digest,
            },
        )
        for item in raw.claims
    }
    claims = (
        tuple(
            item.model_copy(update={"claim_id": claim_aliases[item.claim_id]})
            for item in raw.claims
        )
        if traversable
        else ()
    )
    sources = (
        tuple(
            item.model_copy(
                update={
                    "source_id": _opaque_projection_id(
                        "source",
                        {
                            "source_id": item.source_id,
                            "role": item.role,
                            "artifact_digest": item.artifact_digest,
                        },
                    ),
                    "bound_claim_id": (
                        claim_aliases[item.bound_claim_id]
                        if item.bound_claim_id is not None
                        else None
                    ),
                }
            )
            for item in raw.sources
        )
        if traversable
        else ()
    )
    active_profiles = tuple(
        profile
        for profile in result.request.policy.profiles
        if result.request.fact_ledger is not None
        and profile.applicability is result.request.fact_ledger.applicability
        and raw.assay_protocol_version in profile.approved_assay_protocol_versions
        and raw.controlled_vocabulary_version in profile.approved_controlled_vocabulary_versions
        and raw.unit_system_version in profile.approved_unit_system_versions
    )
    thresholds = (
        {item.metric_code: item for item in active_profiles[0].thresholds}
        if traversable and len(active_profiles) == 1
        else {}
    )
    metrics = (
        tuple(
            ProteinInferenceArtifactQualityMetricReceipt(
                metric_code=item.metric_code,
                observation_state=item.observation_state,
                status=item.status,
                required=item.required,
                direction=thresholds[item.metric_code].direction,
                pass_threshold_ppm=thresholds[item.metric_code].pass_threshold_ppm,
                warning_threshold_ppm=thresholds[item.metric_code].warning_threshold_ppm,
                numerator=item.numerator,
                denominator=item.denominator,
                value_ppm=item.value_ppm,
                censored_count=item.censored_count,
                provenance_digest=sha256_digest(item.provenance),
            )
            for item in result.metrics
        )
        if traversable
        else ()
    )
    applicability = (
        result.request.fact_ledger.applicability
        if traversable and result.request.fact_ledger is not None
        else None
    )
    from glio_proteogen.contracts.m03_05.canonical import (  # noqa: PLC0415
        artifact_quality_receipt_digest,
        claim_binding_digest,
        quality_metric_binding_digest,
        source_binding_digest,
    )

    payload = {
        "receipt_version": M0305_CONTRACT_VERSION,
        "quality_result_digest": result.result_digest,
        "quality_request_digest": result.request_digest,
        "quality_policy_digest": result.policy_digest,
        "quality_configuration_digest": result.configuration_digest,
        "quality_disposition": result.disposition,
        "quality_support_status": result.support.status,
        "quality_human_review_required": result.human_review_required,
        "quality_completed_at": result.completed_at,
        "raw_quality_receipt_digest": result.receipt.raw_quality_receipt_digest,
        "fact_ledger_digest": result.receipt.fact_ledger_digest,
        "quality_profile_digest": result.receipt.profile_digest,
        "admission_result_digest": raw.admission_result_digest,
        "protocol_result_digest": raw.protocol_result_digest,
        "search_space_digest": raw.search_space_digest,
        "search_space_composition": raw.search_space_composition,
        "identity_resolution_digest": raw.identity_resolution_digest,
        "source_manifest_digest": raw.source_manifest_digest,
        "assay_protocol_version": raw.assay_protocol_version,
        "controlled_vocabulary_id": raw.controlled_vocabulary_id,
        "controlled_vocabulary_version": raw.controlled_vocabulary_version,
        "unit_system_version": raw.unit_system_version,
        "applicability": applicability,
        "controls_applicable": (
            active_profiles[0].controls_applicable if len(active_profiles) == 1 else False
        ),
        "source_count": raw.source_count,
        "claim_count": raw.lineage_artifact_count,
        "sources": sources,
        "claims": claims,
        "quality_metrics": metrics,
        "source_binding_digest": source_binding_digest(sources),
        "claim_binding_digest": claim_binding_digest(claims),
        "quality_metric_binding_digest": quality_metric_binding_digest(metrics),
    }
    payload["receipt_digest"] = artifact_quality_receipt_digest(payload)
    return ProteinInferenceArtifactQualityReceipt.model_validate(payload, strict=True)


def _require_authorized_context(context: ExecutionContext) -> None:
    refs = context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize M03-05 artifact detection")
    generic = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic):
        raise ValueError("every generic control must accept M03-05 artifact detection")
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before M03-05 detection")


def _matching_profile(
    request: DetectProteinInferenceArtifactsRequest,
) -> ProteinInferenceArtifactProfile | None:
    receipt = request.quality_receipt
    if receipt.applicability is None:
        return None
    return next(
        (
            profile
            for profile in request.policy.profiles
            if profile.applicability is receipt.applicability
            and receipt.assay_protocol_version in profile.approved_assay_protocol_versions
            and receipt.controlled_vocabulary_version
            in profile.approved_controlled_vocabulary_versions
            and receipt.unit_system_version in profile.approved_unit_system_versions
        ),
        None,
    )


def _validate_ledger_bindings(
    receipt: ProteinInferenceArtifactQualityReceipt,
    ledger: ProteinInferenceArtifactEvidenceLedger,
) -> None:
    _validate_ledger_receipt_bindings(receipt, ledger)
    _validate_unit_bindings(receipt, ledger)


def _validate_ledger_receipt_bindings(
    receipt: ProteinInferenceArtifactQualityReceipt,
    ledger: ProteinInferenceArtifactEvidenceLedger,
) -> None:
    if (
        ledger.quality_result_digest != receipt.quality_result_digest
        or ledger.admission_result_digest != receipt.admission_result_digest
        or ledger.source_manifest_digest != receipt.source_manifest_digest
        or ledger.source_binding_digest != receipt.source_binding_digest
        or ledger.claim_binding_digest != receipt.claim_binding_digest
        or ledger.quality_metric_binding_digest != receipt.quality_metric_binding_digest
        or ledger.applicability is not receipt.applicability
    ):
        raise ValueError("artifact evidence ledger does not bind the compact quality receipt")


def _validate_unit_bindings(
    receipt: ProteinInferenceArtifactQualityReceipt,
    ledger: ProteinInferenceArtifactEvidenceLedger,
) -> None:
    sources = {item.source_id: item for item in receipt.sources}
    claims = {item.claim_id: item for item in receipt.claims}
    for unit in ledger.units:
        if not set(unit.source_ids) <= set(sources) or not set(unit.claim_ids) <= set(claims):
            raise ValueError("artifact unit bindings must be exact receipt subsets")
        if any(
            sources[source_id].role not in M0305_SOURCE_ROLES_BY_UNIT_KIND[unit.unit_kind]
            for source_id in unit.source_ids
        ):
            raise ValueError("artifact unit source role is incompatible with its kind")
        if any(
            claims[claim_id].claim_role not in M0305_CLAIM_ROLES_BY_UNIT_KIND[unit.unit_kind]
            for claim_id in unit.claim_ids
        ):
            raise ValueError("artifact unit claim role is incompatible with its kind")
        for claim_id in unit.claim_ids:
            claim = claims[claim_id]
            anchors = tuple(
                sources[source_id]
                for source_id in unit.source_ids
                if sources[source_id].bound_claim_id == claim_id
                and sources[source_id].role is _RAW_ROLE_BY_CLAIM_ROLE[claim.claim_role]
            )
            if len(anchors) != 1:
                raise ValueError("artifact unit claim requires its exact source anchor")


def _artifact_references(
    request: DetectProteinInferenceArtifactsRequest,
) -> tuple[ArtifactReference, ...]:
    refs = request.context.references
    values = [
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
    ]
    for profile in request.policy.profiles:
        values.append(profile.evidence)
        values.extend(item.evidence for item in profile.thresholds)
    if request.evidence_ledger is not None:
        values.append(request.evidence_ledger.evidence)
    return tuple(values)


def _validate_artifact_reference_consistency(
    request: DetectProteinInferenceArtifactsRequest,
) -> None:
    index: dict[tuple[Identifier, SemanticVersion], tuple[Sha256Digest, NonEmptyStr]] = {}
    for item in _artifact_references(request):
        key = (item.artifact_id, item.version)
        content = (item.digest, item.media_type)
        if key in index and index[key] != content:
            raise ValueError("same artifact identity/version cannot bind conflicting content")
        index[key] = content


def matching_artifact_profile(
    request: DetectProteinInferenceArtifactsRequest,
) -> ProteinInferenceArtifactProfile | None:
    """Return the single profile selected by the policy's disjoint match domains."""

    return _matching_profile(request)


def artifact_ledger_bindings_close(
    request: DetectProteinInferenceArtifactsRequest,
) -> bool:
    ledger = request.evidence_ledger
    if ledger is None or len(ledger.units) > request.policy.max_units:
        return False
    try:
        _validate_ledger_bindings(request.quality_receipt, ledger)
    except ValueError:
        return False
    return True


def _ledger_receipt_bindings_close(
    request: DetectProteinInferenceArtifactsRequest,
) -> bool:
    ledger = request.evidence_ledger
    if ledger is None:
        return False
    try:
        _validate_ledger_receipt_bindings(request.quality_receipt, ledger)
    except ValueError:
        return False
    return True


def _unit_bindings_close(
    request: DetectProteinInferenceArtifactsRequest,
) -> bool:
    ledger = request.evidence_ledger
    if ledger is None:
        return False
    try:
        _validate_unit_bindings(request.quality_receipt, ledger)
    except (KeyError, ValueError):
        return False
    return True


def finding_for(
    code: ProteinInferenceArtifactFindingCode,
    signal_codes: tuple[ProteinInferenceArtifactSignalCode, ...] = (),
    unit_ids: tuple[Identifier, ...] = (),
) -> ProteinInferenceArtifactFinding:
    ordered_signals = tuple(sorted(signal_codes))
    ordered_units = tuple(sorted(unit_ids))
    digest = sha256_digest(
        {
            "code": code,
            "signal_codes": ordered_signals,
            "unit_ids": ordered_units,
        }
    )
    suffix = digest.removeprefix("sha256:")[:16]
    return ProteinInferenceArtifactFinding.model_construct(
        finding_id=f"finding.m0305.{code.value}.{suffix}",
        code=code,
        action=_ACTION_BY_FINDING_CODE[code],
        signal_codes=ordered_signals,
        unit_ids=ordered_units,
        message=_MESSAGE_BY_FINDING_CODE[code],
    )


def _threshold_index(
    profile: ProteinInferenceArtifactProfile,
) -> dict[ProteinInferenceArtifactSignalCode, ProteinInferenceArtifactThreshold]:
    return {item.signal_code: item for item in profile.thresholds}


def _signal_provenance(
    request: DetectProteinInferenceArtifactsRequest,
    *,
    evidence_ledger_digest: Sha256Digest,
    profile_digest: Sha256Digest,
    threshold_digest: Sha256Digest,
) -> ProteinInferenceArtifactSignalProvenance:
    receipt = request.quality_receipt
    return ProteinInferenceArtifactSignalProvenance(
        quality_result_digest=receipt.quality_result_digest,
        evidence_ledger_digest=evidence_ledger_digest,
        profile_digest=profile_digest,
        threshold_digest=threshold_digest,
        source_binding_digest=receipt.source_binding_digest,
        claim_binding_digest=receipt.claim_binding_digest,
        quality_metric_binding_digest=receipt.quality_metric_binding_digest,
    )


def _flag_for_observed(
    signal: ProteinInferenceArtifactSignal,
    threshold: ProteinInferenceArtifactThreshold,
) -> ProteinInferenceArtifactFlagState:
    if signal.evaluated_count == 0:
        return ProteinInferenceArtifactFlagState.INDETERMINATE
    evidence_product = signal.supporting_count * M0305_RATE_SCALE
    if evidence_product >= threshold.exclude_threshold_ppm * signal.evaluated_count:
        return ProteinInferenceArtifactFlagState.DETECTED
    if evidence_product >= threshold.review_threshold_ppm * signal.evaluated_count:
        return ProteinInferenceArtifactFlagState.SUSPECTED
    return ProteinInferenceArtifactFlagState.CLEAR


def expected_signal_scores(
    request: DetectProteinInferenceArtifactsRequest,
    profile: ProteinInferenceArtifactProfile | None = None,
) -> tuple[ProteinInferenceArtifactSignalScore, ...]:
    ledger = request.evidence_ledger
    active = profile if profile is not None else _matching_profile(request)
    if (
        ledger is None
        or active is None
        or len(ledger.units) > request.policy.max_units
        or not artifact_ledger_bindings_close(request)
    ):
        return ()
    from glio_proteogen.contracts.m03_05.canonical import (  # noqa: PLC0415
        artifact_evidence_ledger_digest,
        profile_digest,
        threshold_digest,
    )

    ledger_hash = artifact_evidence_ledger_digest(ledger)
    profile_hash = profile_digest(active)
    thresholds = _threshold_index(active)
    threshold_hashes = {code: threshold_digest(threshold) for code, threshold in thresholds.items()}
    scores: list[ProteinInferenceArtifactSignalScore] = []
    for unit in ledger.units:
        for signal in unit.signals:
            threshold = thresholds[signal.signal_code]
            if signal.observation_state is ProteinInferenceArtifactObservationState.OBSERVED:
                score = (
                    None
                    if signal.evaluated_count == 0
                    else (signal.supporting_count * M0305_RATE_SCALE + signal.evaluated_count // 2)
                    // signal.evaluated_count
                )
                supporting: int | None = signal.supporting_count
                evaluated: int | None = signal.evaluated_count
                flag = _flag_for_observed(signal, threshold)
            else:
                score = supporting = evaluated = None
                flag = (
                    ProteinInferenceArtifactFlagState.NOT_APPLICABLE
                    if signal.observation_state
                    is ProteinInferenceArtifactObservationState.NOT_APPLICABLE
                    else ProteinInferenceArtifactFlagState.INDETERMINATE
                )
            scores.append(
                ProteinInferenceArtifactSignalScore(
                    unit_id=unit.unit_id,
                    unit_kind=unit.unit_kind,
                    signal_code=signal.signal_code,
                    observation_state=signal.observation_state,
                    flag_state=flag,
                    supporting_count=supporting,
                    evaluated_count=evaluated,
                    evidence_score_ppm=score,
                    required=threshold.required,
                    provenance=_signal_provenance(
                        request,
                        evidence_ledger_digest=ledger_hash,
                        profile_digest=profile_hash,
                        threshold_digest=threshold_hashes[signal.signal_code],
                    ),
                )
            )
    return tuple(sorted(scores, key=canonical_json_bytes))


def _unit_provenance(
    score: ProteinInferenceArtifactSignalScore,
) -> ProteinInferenceArtifactUnitProvenance:
    provenance = score.provenance
    return ProteinInferenceArtifactUnitProvenance(
        quality_result_digest=provenance.quality_result_digest,
        evidence_ledger_digest=provenance.evidence_ledger_digest,
        profile_digest=provenance.profile_digest,
        source_binding_digest=provenance.source_binding_digest,
        claim_binding_digest=provenance.claim_binding_digest,
        quality_metric_binding_digest=provenance.quality_metric_binding_digest,
    )


def expected_artifact_posteriors(
    scores: tuple[ProteinInferenceArtifactSignalScore, ...],
) -> tuple[ProteinInferenceArtifactPosterior, ...]:
    grouped: dict[Identifier, list[ProteinInferenceArtifactSignalScore]] = {}
    for score in scores:
        grouped.setdefault(score.unit_id, []).append(score)
    posteriors: list[ProteinInferenceArtifactPosterior] = []
    precedence = (
        (
            ProteinInferenceArtifactFlagState.DETECTED,
            ProteinInferenceArtifactPosteriorState.DETECTED,
        ),
        (
            ProteinInferenceArtifactFlagState.SUSPECTED,
            ProteinInferenceArtifactPosteriorState.SUSPECTED,
        ),
        (
            ProteinInferenceArtifactFlagState.INDETERMINATE,
            ProteinInferenceArtifactPosteriorState.INDETERMINATE,
        ),
        (
            ProteinInferenceArtifactFlagState.CLEAR,
            ProteinInferenceArtifactPosteriorState.CLEAR,
        ),
    )
    for unit_id, unit_scores in grouped.items():
        selected_flag, state = next(
            (flag, posterior)
            for flag, posterior in precedence
            if any(item.flag_state is flag for item in unit_scores)
        )
        contributing = tuple(
            sorted(item.signal_code for item in unit_scores if item.flag_state is selected_flag)
        )
        values = tuple(
            item.evidence_score_ppm for item in unit_scores if item.evidence_score_ppm is not None
        )
        posteriors.append(
            ProteinInferenceArtifactPosterior(
                unit_id=unit_id,
                state=state,
                max_evidence_score_ppm=max(values) if values else None,
                contributing_signal_codes=contributing,
                provenance=_unit_provenance(unit_scores[0]),
            )
        )
    return tuple(sorted(posteriors, key=canonical_json_bytes))


def expected_contamination_flags(
    scores: tuple[ProteinInferenceArtifactSignalScore, ...],
) -> tuple[ProteinInferenceContaminationFlag, ...]:
    flags: list[ProteinInferenceContaminationFlag] = []
    for item in scores:
        if (
            item.signal_code not in M0305_CONTAMINATION_SIGNALS
            or item.flag_state
            not in {
                ProteinInferenceArtifactFlagState.SUSPECTED,
                ProteinInferenceArtifactFlagState.DETECTED,
            }
            or item.evidence_score_ppm is None
        ):
            continue
        state: Literal[
            ProteinInferenceArtifactFlagState.SUSPECTED,
            ProteinInferenceArtifactFlagState.DETECTED,
        ] = (
            ProteinInferenceArtifactFlagState.DETECTED
            if item.flag_state is ProteinInferenceArtifactFlagState.DETECTED
            else ProteinInferenceArtifactFlagState.SUSPECTED
        )
        flags.append(
            ProteinInferenceContaminationFlag(
                unit_id=item.unit_id,
                signal_code=item.signal_code,
                state=state,
                evidence_score_ppm=item.evidence_score_ppm,
                provenance=item.provenance,
            )
        )
    return tuple(sorted(flags, key=canonical_json_bytes))


def expected_exclusion_mask(
    posteriors: tuple[ProteinInferenceArtifactPosterior, ...],
) -> ProteinInferenceEvidenceExclusionMask:
    return ProteinInferenceEvidenceExclusionMask(
        retain_unit_ids=tuple(
            sorted(
                item.unit_id
                for item in posteriors
                if item.state is ProteinInferenceArtifactPosteriorState.CLEAR
            )
        ),
        review_unit_ids=tuple(
            sorted(
                item.unit_id
                for item in posteriors
                if item.state
                in {
                    ProteinInferenceArtifactPosteriorState.SUSPECTED,
                    ProteinInferenceArtifactPosteriorState.INDETERMINATE,
                }
            )
        ),
        exclude_unit_ids=tuple(
            sorted(
                item.unit_id
                for item in posteriors
                if item.state is ProteinInferenceArtifactPosteriorState.DETECTED
            )
        ),
    )


def _safe_failure_finding(  # noqa: PLR0911 - explicit safety precedence.
    request: DetectProteinInferenceArtifactsRequest,
) -> ProteinInferenceArtifactFinding | None:
    receipt = request.quality_receipt
    upstream = {
        ProteinInferenceQualityDisposition.REJECTED: (
            ProteinInferenceArtifactFindingCode.UPSTREAM_REJECTED
        ),
        ProteinInferenceQualityDisposition.QUARANTINED: (
            ProteinInferenceArtifactFindingCode.UPSTREAM_QUARANTINED
        ),
        ProteinInferenceQualityDisposition.ABSTAINED: (
            ProteinInferenceArtifactFindingCode.UPSTREAM_ABSTAINED
        ),
    }.get(receipt.quality_disposition)
    if upstream is not None:
        return finding_for(upstream)
    if (
        receipt.quality_support_status is SupportStatus.LIMITED
        or receipt.quality_human_review_required
    ):
        return finding_for(ProteinInferenceArtifactFindingCode.UPSTREAM_REVIEW_REQUIRED)
    if (
        receipt.source_count > request.policy.max_sources
        or receipt.claim_count > request.policy.max_claims
        or (
            request.evidence_ledger is not None
            and len(request.evidence_ledger.units) > request.policy.max_units
        )
    ):
        return finding_for(ProteinInferenceArtifactFindingCode.UPSTREAM_SHAPE_UNSUPPORTED)
    if request.evidence_ledger is None:
        return finding_for(ProteinInferenceArtifactFindingCode.UPSTREAM_SHAPE_UNSUPPORTED)
    if not _ledger_receipt_bindings_close(request):
        return finding_for(ProteinInferenceArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH)
    if not _unit_bindings_close(request):
        return finding_for(ProteinInferenceArtifactFindingCode.EVIDENCE_UNIT_BINDING_CONFLICT)
    if _matching_profile(request) is None:
        return finding_for(ProteinInferenceArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED)
    return None


def expected_artifact_findings(
    request: DetectProteinInferenceArtifactsRequest,
    scores: tuple[ProteinInferenceArtifactSignalScore, ...] = (),
    contamination_flags: tuple[ProteinInferenceContaminationFlag, ...] = (),
) -> tuple[ProteinInferenceArtifactFinding, ...]:
    safe_failure = _safe_failure_finding(request)
    if safe_failure is not None:
        return (safe_failure,)
    findings: list[ProteinInferenceArtifactFinding] = []
    for code in ProteinInferenceArtifactSignalCode:
        by_signal = tuple(item for item in scores if item.signal_code is code)
        detected_ids = tuple(
            item.unit_id
            for item in by_signal
            if item.flag_state is ProteinInferenceArtifactFlagState.DETECTED
        )
        suspected_ids = tuple(
            item.unit_id
            for item in by_signal
            if item.flag_state is ProteinInferenceArtifactFlagState.SUSPECTED
        )
        if detected_ids:
            findings.append(
                finding_for(
                    ProteinInferenceArtifactFindingCode.ARTIFACT_DETECTED,
                    signal_codes=(code,),
                    unit_ids=detected_ids,
                )
            )
        elif suspected_ids:
            findings.append(
                finding_for(
                    ProteinInferenceArtifactFindingCode.ARTIFACT_SUSPECTED,
                    signal_codes=(code,),
                    unit_ids=suspected_ids,
                )
            )
        issue_precedence = (
            (
                ProteinInferenceArtifactObservationState.MISSING,
                ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_MISSING,
            ),
            (
                ProteinInferenceArtifactObservationState.UNSUPPORTED,
                ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_UNSUPPORTED,
            ),
            (
                ProteinInferenceArtifactObservationState.OBSERVED,
                ProteinInferenceArtifactFindingCode.SIGNAL_NOT_EVALUABLE,
            ),
        )
        for state, finding_code in issue_precedence:
            unit_ids = tuple(
                item.unit_id
                for item in by_signal
                if item.required
                and item.observation_state is state
                and item.flag_state is ProteinInferenceArtifactFlagState.INDETERMINATE
            )
            if unit_ids:
                findings.append(
                    finding_for(
                        finding_code,
                        signal_codes=(code,),
                        unit_ids=unit_ids,
                    )
                )
        optional_ids = tuple(
            item.unit_id
            for item in by_signal
            if not item.required
            and item.flag_state is ProteinInferenceArtifactFlagState.INDETERMINATE
        )
        if optional_ids:
            existing = next(
                (
                    item
                    for item in findings
                    if item.code is ProteinInferenceArtifactFindingCode.SIGNAL_NOT_EVALUABLE
                    and item.signal_codes == (code,)
                ),
                None,
            )
            if existing is not None:
                findings.remove(existing)
                optional_ids = (*existing.unit_ids, *optional_ids)
            findings.append(
                finding_for(
                    ProteinInferenceArtifactFindingCode.SIGNAL_NOT_EVALUABLE,
                    signal_codes=(code,),
                    unit_ids=tuple(sorted(optional_ids)),
                )
            )
        contamination_ids = tuple(
            item.unit_id for item in contamination_flags if item.signal_code is code
        )
        if contamination_ids:
            findings.append(
                finding_for(
                    ProteinInferenceArtifactFindingCode.CONTAMINATION_FLAGGED,
                    signal_codes=(code,),
                    unit_ids=contamination_ids,
                )
            )
    return tuple(sorted(findings, key=canonical_json_bytes))


def expected_disposition(  # noqa: PLR0911 - explicit safety precedence.
    request: DetectProteinInferenceArtifactsRequest,
    scores: tuple[ProteinInferenceArtifactSignalScore, ...] = (),
    findings: tuple[ProteinInferenceArtifactFinding, ...] = (),
) -> ProteinInferenceArtifactDisposition:
    del findings
    upstream = request.quality_receipt.quality_disposition
    if upstream is ProteinInferenceQualityDisposition.REJECTED:
        return ProteinInferenceArtifactDisposition.REJECTED
    if upstream is ProteinInferenceQualityDisposition.QUARANTINED:
        return ProteinInferenceArtifactDisposition.QUARANTINED
    if upstream is ProteinInferenceQualityDisposition.ABSTAINED:
        return ProteinInferenceArtifactDisposition.ABSTAINED
    failure = _safe_failure_finding(request)
    if failure is not None:
        if failure.action is ProteinInferenceArtifactFindingAction.QUARANTINE:
            return ProteinInferenceArtifactDisposition.QUARANTINED
        return ProteinInferenceArtifactDisposition.ABSTAINED
    if any(
        item.flag_state
        in {
            ProteinInferenceArtifactFlagState.SUSPECTED,
            ProteinInferenceArtifactFlagState.DETECTED,
        }
        for item in scores
    ):
        return ProteinInferenceArtifactDisposition.QUARANTINED
    if any(
        item.required and item.flag_state is ProteinInferenceArtifactFlagState.INDETERMINATE
        for item in scores
    ):
        return ProteinInferenceArtifactDisposition.ABSTAINED
    if any(item.flag_state is ProteinInferenceArtifactFlagState.INDETERMINATE for item in scores):
        return ProteinInferenceArtifactDisposition.ABSTAINED
    return ProteinInferenceArtifactDisposition.CLEARED


def expected_computation_receipt(
    request: DetectProteinInferenceArtifactsRequest,
    disposition: ProteinInferenceArtifactDisposition,
    profile: ProteinInferenceArtifactProfile | None = None,
) -> ProteinInferenceArtifactComputationReceipt:
    from glio_proteogen.contracts.m03_05.canonical import (  # noqa: PLC0415
        artifact_evidence_ledger_digest,
        artifact_quality_receipt_digest,
        configuration_digest,
        policy_digest,
        profile_digest,
    )

    active = profile if profile is not None else _matching_profile(request)
    ledger = request.evidence_ledger
    return ProteinInferenceArtifactComputationReceipt(
        artifact_quality_receipt_digest=artifact_quality_receipt_digest(request.quality_receipt),
        evidence_ledger_digest=(
            artifact_evidence_ledger_digest(ledger) if ledger is not None else None
        ),
        policy_digest=policy_digest(request.policy),
        configuration_digest=configuration_digest(request.policy),
        profile_digest=profile_digest(active) if active is not None else None,
        supersedes_result_digest=request.supersedes_result_digest,
        disposition=disposition,
    )


def expected_support(
    disposition: ProteinInferenceArtifactDisposition,
) -> SupportDecision:
    if disposition is ProteinInferenceArtifactDisposition.CLEARED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="protein_inference_artifact_screen_cleared",
            rationale="No applicable artifact signal reached a reviewed action threshold.",
        )
    if disposition is ProteinInferenceArtifactDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="protein_inference_artifact_screen_quarantined",
            rationale="Artifact evidence or a binding contradiction requires review.",
        )
    reason = (
        "protein_inference_artifact_screen_rejected"
        if disposition is ProteinInferenceArtifactDisposition.REJECTED
        else "protein_inference_artifact_screen_abstained"
    )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code=reason,
        rationale="The upstream state, graph shape, or required evidence is unsupported.",
    )


def expected_uncertainty(
    disposition: ProteinInferenceArtifactDisposition,
) -> UncertaintyProfile:
    del disposition
    values = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0305_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=values[0],
        sampling=values[1],
        parameter=values[2],
        model_form=values[3],
        identification=values[4],
        support=values[5],
        transport=values[6],
        sensitivity_notes=M0305_SENSITIVITY_NOTES,
    )


def expected_control_decisions(
    request: DetectProteinInferenceArtifactsRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    records = (
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
    return tuple(sorted(records, key=lambda item: item.role.value))


def artifact_evidence_index(
    request: DetectProteinInferenceArtifactsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    active = _matching_profile(request)
    artifacts = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
        *((active.evidence,) if active is not None else ()),
        *((item.evidence for item in active.thresholds) if active else ()),
        *((request.evidence_ledger.evidence,) if request.evidence_ledger else ()),
    )
    unique = {
        (item.artifact_id, item.version, item.digest, item.media_type): item for item in artifacts
    }
    return tuple(
        EvidenceReference(
            reference=unique[key],
            role="evidence",
            claim=M0305_EVIDENCE_CLAIM,
        )
        for key in sorted(unique, key=canonical_json_bytes)
    )


def expected_provenance(
    request: DetectProteinInferenceArtifactsRequest,
    disposition: ProteinInferenceArtifactDisposition,
) -> ProvenanceRecord:
    del disposition
    from glio_proteogen.contracts.m03_05.canonical import (  # noqa: PLC0415
        artifact_evidence_ledger_digest,
        artifact_quality_receipt_digest,
        canonical_request_digest,
        configuration_digest,
    )

    ledger = request.evidence_ledger
    digests = [
        artifact_quality_receipt_digest(request.quality_receipt),
        canonical_request_digest(request),
    ]
    if ledger is not None:
        digests.append(artifact_evidence_ledger_digest(ledger))
    if request.supersedes_result_digest is not None:
        digests.append(request.supersedes_result_digest)
    return ProvenanceRecord(
        activity_id=("activity.m0305." + canonical_request_digest(request).removeprefix("sha256:")),
        actor_id=request.context.actor_id,
        module_id=M0305_MODULE_ID,
        module_version=M0305_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(digests)),
        configuration_digest=configuration_digest(request.policy),
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=expected_control_decisions(request),
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code=M0305_DETECTOR_LIMITATION_CODE,
                    statement=(
                        "This output owns only categorical artifact state, contamination "
                        "flags, and an evidence exclusion/review mask; it does not infer "
                        "protein, proteoform, complex, or kinase activity."
                    ),
                ),
                Limitation(
                    code=M0305_SCORE_LIMITATION_CODE,
                    statement=(
                        "evidence_score_ppm is a deterministic integer evidence fraction "
                        "and is not a calibrated posterior probability."
                    ),
                ),
                Limitation(
                    code=M0305_AUTHORITY_LIMITATION_CODE,
                    statement=(
                        "The compact M03-04 receipt proves caller-declared content "
                        "self-consistency, not execution authenticity or external control "
                        "authority."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


expected_scores = expected_signal_scores
expected_posteriors = expected_artifact_posteriors
expected_findings = expected_artifact_findings


__all__ = [name for name in globals() if name.startswith(("M0305_", "ProteinInference"))] + [
    "DetectProteinInferenceArtifactsRequest",
    "artifact_quality_receipt",
]
