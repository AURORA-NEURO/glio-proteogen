"""Strict M04-01 proteoform protocol and metadata contracts."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m04_01.canonical import (
    canonical_request_digest,
    configuration_digest,
    coordinate_policy_digest,
    profile_digest,
    protocol_digest,
    protocol_section_digest,
    receipt_digest,
    reference_bundle_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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
    Limitation,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0401_MODULE_ID: Final = "GLIO-PROTEOGEN-M04-01"
M0401_CONTRACT_VERSION: Final = "1.0.0"
M0401_OPERATION: Final = "evaluate_proteoform_protocol"
M0401_PARENT_TARGET: Final = "protein_rna_discordance"
M0401_RATE_SCALE: Final = 1_000_000
M0401_SECTION_COUNT: Final = 11
M0401_IDENTITY_KEY_COUNT: Final = 7
M0401_UNRESOLVED_STATE_COUNT: Final = 10
M0401_HANDOFF_ROLE_COUNT: Final = 8
M0401_EVIDENCE_COUNT: Final = 21
M0401_LIMITATION_COUNT: Final = 3
M0401_MAX_APPROVED_REFERENCE_BUNDLES: Final = 64
M0401_MAX_APPROVED_VERSIONS: Final = 32
M0401_MAX_COORDINATE_PROFILES: Final = 8
M0401_MAX_QUANTIFICATION_PAIRS: Final = 16
M0401_MAX_EVIDENCE_CLASSES: Final = 5
M0401_MAX_LABILE_HANDLINGS: Final = 3
M0401_MAX_ISOFORM_DISCRIMINATORS: Final = 16
M0401_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0401_MAX_GENE_RECORDS: Final = 10_000_000
M0401_MAX_TRANSCRIPT_RECORDS: Final = 250_000_000
M0401_MAX_CANONICAL_PROTEIN_SEQUENCES: Final = 250_000_000
M0401_MAX_ISOFORM_SEQUENCES: Final = 250_000_000
M0401_MAX_TRANSCRIPT_PROTEIN_EDGES: Final = 500_000_000
M0401_MAX_MODIFICATION_TERMS: Final = 10_000_000

M0401_CONFORMANT_SUPPORT_RATIONALE: Final = (
    "The declared proteoform protocol conforms to its exact reviewed profile."
)
M0401_QUARANTINED_SUPPORT_RATIONALE: Final = (
    "One or more reviewed proteoform protocol constraints failed and require review."
)
M0401_UNCERTAINTY_RATIONALES: Final = (
    "M04-01 does not inspect proteomic or transcriptomic measurements.",
    "M04-01 does not estimate sampling uncertainty.",
    "The deterministic protocol evaluator fits no parameters.",
    "M04-01 executes no learned proteoform model.",
    "No proteoform identification or modification localization is performed.",
    "Support is a deterministic reviewed-profile decision.",
    "External reference and control authorities are caller-declared.",
)
M0401_SENSITIVITY_NOTES: Final = (
    "A reviewed-domain mismatch quarantines the declarations without changing them.",
    "Missing, ambiguous, and below-detection evidence remain explicit non-negative states.",
)

_OPAQUE_IDENTIFIER = re.compile(
    r"^(?:request|actor|decision|schema|profile|bundle|vocabulary|reviewer|evidence)"
    r"\.[0-9a-f]{64}$"
)
_LOWERCASE_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")
_ALLOWED_MEDIA_TYPES: Final = frozenset(
    {
        "application/vnd.glio-proteogen.control+json",
        "application/vnd.glio-proteogen.m04-01.reference+json",
        "application/vnd.glio-proteogen.m04-01.policy+json",
        "application/vnd.glio-proteogen.m04-01.profile+json",
        "application/vnd.glio-proteogen.m04-01.manifest+json",
    }
)

type ProteoformProtocolOpaqueNamespace = Literal[
    "request",
    "actor",
    "decision",
    "schema",
    "profile",
    "bundle",
    "vocabulary",
    "reviewer",
    "evidence",
]


class ProteoformApplicability(StrEnum):
    BOTTOM_UP_DDA = "bottom_up_dda"
    BOTTOM_UP_DIA = "bottom_up_dia"
    TOP_DOWN = "top_down"
    TARGETED = "targeted"


class ProteoformEvidenceClass(StrEnum):
    ISOFORM_UNIQUE_PEPTIDE = "isoform_unique_peptide"
    SPLICE_JUNCTION_PEPTIDE = "splice_junction_peptide"
    SEQUENCE_VARIANT_PEPTIDE = "sequence_variant_peptide"
    TERMINAL_PEPTIDE = "terminal_peptide"
    INTACT_PROTEOFORM = "intact_proteoform"


class ModificationLocalizationState(StrEnum):
    LOCALIZED = "localized"
    AMBIGUOUS_SITE_SET = "ambiguous_site_set"
    UNLOCALIZED = "unlocalized"
    NOT_EVALUABLE = "not_evaluable"


class LabileModificationHandling(StrEnum):
    PRESERVE_SITE_SET = "preserve_site_set"
    REQUIRE_SITE_DETERMINING_EVIDENCE = "require_site_determining_evidence"
    UNSUPPORTED = "unsupported"


class ProteinQuantificationUnit(StrEnum):
    LINEAR_INTENSITY = "linear_intensity"
    NORMALIZED_INTENSITY = "normalized_intensity"
    MOLAR_FRACTION = "molar_fraction"


class TranscriptQuantificationUnit(StrEnum):
    TPM = "tpm"
    NORMALIZED_COUNT = "normalized_count"


class ProteoformQuantificationScale(StrEnum):
    LINEAR = "linear"
    LOG2 = "log2"


class CoordinateConvention(StrEnum):
    ONE_BASED_CLOSED = "one_based_closed"
    ZERO_BASED_HALF_OPEN = "zero_based_half_open"


ProteoformAssayApplicability = ProteoformApplicability
ProteoformLocalizationState = ModificationLocalizationState
ProteinQuantityUnit = ProteinQuantificationUnit
TranscriptQuantityUnit = TranscriptQuantificationUnit
QuantityScale = ProteoformQuantificationScale


class ProteoformIdentityKey(StrEnum):
    PATIENT = "patient_id"
    SPECIMEN = "specimen_id"
    ALIQUOT = "aliquot_id"
    SECTION = "section_id"
    ANALYTE = "analyte_id"
    RUN = "run_id"
    DERIVED_OBJECT = "derived_object_id"


class ProteoformUnresolvedState(StrEnum):
    MISSING = "missing"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"
    REDACTED = "redacted"
    NOT_DETECTED = "not_detected"
    BELOW_DETECTION_LIMIT = "below_detection_limit"
    ISOFORM_AMBIGUOUS = "isoform_ambiguous"
    SITE_AMBIGUOUS = "site_ambiguous"


class ProteinRnaDiscordanceHandoffRole(StrEnum):
    REFERENCE_BUNDLE = "reference_bundle"
    TRANSCRIPT_PROTEIN_MAPPING = "transcript_protein_mapping"
    COORDINATE_MAPPING = "coordinate_mapping"
    ISOFORM_DISCRIMINATION = "isoform_discrimination"
    MODIFICATION_LOCALIZATION = "modification_localization"
    QUANTIFICATION_UNITS = "quantification_units"
    UNRESOLVED_STATES = "unresolved_states"
    PROVENANCE = "provenance"


class ProteoformProtocolSection(StrEnum):
    APPLICABILITY = "applicability"
    IDENTITY = "identity"
    METADATA_VERSIONS = "metadata_versions"
    REFERENCE_BUNDLE = "reference_bundle"
    COORDINATE_MAPPING = "coordinate_mapping"
    EVIDENCE_ELIGIBILITY = "evidence_eligibility"
    ISOFORM_DISCRIMINATION = "isoform_discrimination"
    MODIFICATION_LOCALIZATION = "modification_localization"
    QUANTIFICATION = "quantification"
    UNRESOLVED_SEMANTICS = "unresolved_semantics"
    DISCORDANCE_HANDOFF = "discordance_handoff"


_PROTOCOL_SECTION_ORDER: Final = {
    section: index for index, section in enumerate(ProteoformProtocolSection)
}


class ProteoformProtocolFindingState(StrEnum):
    PASS = "pass"  # noqa: S105 - conformance state, not a secret.
    FAIL = "fail"


class ProteoformProtocolConformanceStatus(StrEnum):
    CONFORMANT = "conformant"
    NONCONFORMANT = "nonconformant"


class ProteoformProtocolConformanceDisposition(StrEnum):
    CONFORMANT = "conformant"
    QUARANTINED = "quarantined"


def opaque_proteoform_protocol_identifier(
    namespace: ProteoformProtocolOpaqueNamespace,
    value: str,
) -> Identifier:
    """Validate one opaque, content-derived M04-01 identifier."""

    if not value.startswith(f"{namespace}.") or _OPAQUE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"identifier must be an opaque {namespace} digest alias")
    return value


def _owned_artifact(
    value: ArtifactReference,
    *,
    media_types: frozenset[str] = _ALLOWED_MEDIA_TYPES,
) -> ArtifactReference:
    opaque_proteoform_protocol_identifier("evidence", value.artifact_id)
    if (
        _LOWERCASE_MEDIA_TYPE.fullmatch(value.media_type) is None
        or value.media_type not in media_types
    ):
        raise ValueError("M04-01 evidence media type is not in the governed lowercase allowlist")
    return value


def _canonical(values: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def _unique(values: tuple[object, ...], message: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(message)


def _strict_bool(value: object) -> object:
    if type(value) is not bool:
        raise ValueError("governed safety declarations require strict booleans")
    return value


class ProteoformReferenceCardinality(FrozenModel):
    gene_records: int = Field(gt=0, le=M0401_MAX_GENE_RECORDS)
    transcript_records: int = Field(gt=0, le=M0401_MAX_TRANSCRIPT_RECORDS)
    canonical_protein_sequences: int = Field(gt=0, le=M0401_MAX_CANONICAL_PROTEIN_SEQUENCES)
    isoform_sequences: int = Field(gt=0, le=M0401_MAX_ISOFORM_SEQUENCES)
    mapped_transcripts: int = Field(gt=0, le=M0401_MAX_TRANSCRIPT_RECORDS)
    mapped_protein_sequences: int = Field(
        gt=0,
        le=M0401_MAX_CANONICAL_PROTEIN_SEQUENCES + M0401_MAX_ISOFORM_SEQUENCES,
    )
    transcript_protein_edges: int = Field(gt=0, le=M0401_MAX_TRANSCRIPT_PROTEIN_EDGES)
    modification_terms: int = Field(gt=0, le=M0401_MAX_MODIFICATION_TERMS)

    @model_validator(mode="after")
    def cardinalities_close(self) -> ProteoformReferenceCardinality:
        protein_total = self.canonical_protein_sequences + self.isoform_sequences
        lower_edges = max(self.mapped_transcripts, self.mapped_protein_sequences)
        upper_edges = self.mapped_transcripts * self.mapped_protein_sequences
        if self.gene_records > self.transcript_records:
            raise ValueError("gene records cannot exceed transcript records")
        if self.mapped_transcripts > self.transcript_records:
            raise ValueError("mapped transcripts cannot exceed transcript records")
        if self.mapped_protein_sequences > protein_total:
            raise ValueError("mapped protein sequences cannot exceed declared protein sequences")
        if not lower_edges <= self.transcript_protein_edges <= upper_edges:
            raise ValueError("transcript-protein edges do not close over mapped records")
        return self


class ProteoformReferenceBundle(FrozenModel):
    bundle_id: Identifier
    version: SemanticVersion
    cardinality: ProteoformReferenceCardinality
    genome_reference: ArtifactReference
    transcript_annotation_reference: ArtifactReference
    canonical_protein_reference: ArtifactReference
    isoform_reference: ArtifactReference
    transcript_protein_mapping_reference: ArtifactReference
    modification_vocabulary_reference: ArtifactReference
    bundle_manifest_reference: ArtifactReference

    @field_validator("bundle_id")
    @classmethod
    def bundle_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("bundle", value)

    @field_validator(
        "genome_reference",
        "transcript_annotation_reference",
        "canonical_protein_reference",
        "isoform_reference",
        "transcript_protein_mapping_reference",
        "modification_vocabulary_reference",
    )
    @classmethod
    def references_are_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.reference+json"}),
        )

    @field_validator("bundle_manifest_reference")
    @classmethod
    def manifest_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.manifest+json"}),
        )

    @model_validator(mode="after")
    def artifacts_are_distinct(self) -> ProteoformReferenceBundle:
        artifacts = (
            self.genome_reference,
            self.transcript_annotation_reference,
            self.canonical_protein_reference,
            self.isoform_reference,
            self.transcript_protein_mapping_reference,
            self.modification_vocabulary_reference,
            self.bundle_manifest_reference,
        )
        if len({item.artifact_id for item in artifacts}) != len(artifacts) or len(
            {item.digest for item in artifacts}
        ) != len(artifacts):
            raise ValueError("reference bundle requires seven distinct artifacts and digests")
        return self


class ProteoformCoordinatePolicy(FrozenModel):
    genome_convention: CoordinateConvention
    transcript_convention: CoordinateConvention
    protein_convention: CoordinateConvention
    coordinate_mapping_version: SemanticVersion
    conversion_is_explicit: Literal[True] = True
    reference_allele_validation_required: Literal[True] = True
    sequence_residue_validation_required: Literal[True] = True
    insertions_and_deletions_explicit: Literal[True] = True
    mismatches_remain_unresolved: Literal[True] = True

    @field_validator(
        "conversion_is_explicit",
        "reference_allele_validation_required",
        "sequence_residue_validation_required",
        "insertions_and_deletions_explicit",
        "mismatches_remain_unresolved",
        mode="before",
    )
    @classmethod
    def booleans_are_strict(cls, value: object) -> object:
        return _strict_bool(value)


class ProteoformEvidenceEligibilityPolicy(FrozenModel):
    eligible_evidence_classes: tuple[ProteoformEvidenceClass, ...] = Field(
        min_length=1,
        max_length=M0401_MAX_EVIDENCE_CLASSES,
    )
    uniqueness_relative_to_reference_bundle: Literal[True] = True
    sequence_variant_requires_genome_support: Literal[True] = True
    splice_junction_requires_transcript_support: Literal[True] = True
    terminal_peptide_requires_processing_annotation: Literal[True] = True
    intact_proteoform_requires_mass_envelope: Literal[True] = True
    shared_evidence_supports_group_claims_only: Literal[True] = True
    evidence: ArtifactReference

    @field_validator(
        "uniqueness_relative_to_reference_bundle",
        "sequence_variant_requires_genome_support",
        "splice_junction_requires_transcript_support",
        "terminal_peptide_requires_processing_annotation",
        "intact_proteoform_requires_mass_envelope",
        "shared_evidence_supports_group_claims_only",
        mode="before",
    )
    @classmethod
    def booleans_are_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @field_validator("eligible_evidence_classes")
    @classmethod
    def classes_are_canonical(
        cls, values: tuple[ProteoformEvidenceClass, ...]
    ) -> tuple[ProteoformEvidenceClass, ...]:
        return tuple(sorted(values, key=str))

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.policy+json"}),
        )

    @model_validator(mode="after")
    def classes_are_unique(self) -> ProteoformEvidenceEligibilityPolicy:
        _unique(self.eligible_evidence_classes, "eligible evidence classes must be unique")
        return self


class IsoformDiscriminationPolicy(FrozenModel):
    accepted_discriminators: tuple[ProteoformEvidenceClass, ...] = Field(
        min_length=1, max_length=M0401_MAX_EVIDENCE_CLASSES
    )
    minimum_independent_discriminators: int = Field(gt=0, le=M0401_MAX_ISOFORM_DISCRIMINATORS)
    exact_reference_mapping_required: Literal[True] = True
    ambiguous_evidence_preserves_candidate_set: Literal[True] = True
    shared_evidence_never_promotes_isoform: Literal[True] = True
    absent_discriminator_is_not_nondetection: Literal[True] = True
    nondetection_requires_declared_detection_limit: Literal[True] = True
    evidence: ArtifactReference

    @field_validator(
        "exact_reference_mapping_required",
        "ambiguous_evidence_preserves_candidate_set",
        "shared_evidence_never_promotes_isoform",
        "absent_discriminator_is_not_nondetection",
        "nondetection_requires_declared_detection_limit",
        mode="before",
    )
    @classmethod
    def booleans_are_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @field_validator("accepted_discriminators")
    @classmethod
    def discriminators_are_canonical(
        cls, values: tuple[ProteoformEvidenceClass, ...]
    ) -> tuple[ProteoformEvidenceClass, ...]:
        return tuple(sorted(values, key=str))

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.policy+json"}),
        )

    @model_validator(mode="after")
    def discriminators_are_unique(self) -> IsoformDiscriminationPolicy:
        _unique(self.accepted_discriminators, "isoform discriminators must be unique")
        return self


class ModificationLocalizationPolicy(FrozenModel):
    declared_states: tuple[ModificationLocalizationState, ...] = Field(min_length=4, max_length=4)
    score_scale: Literal["integer_ppm"] = "integer_ppm"
    minimum_localized_probability_ppm: int = Field(ge=0, le=M0401_RATE_SCALE)
    higher_is_more_localized: Literal[True] = True
    ambiguous_site_sets_preserved: Literal[True] = True
    unlocalized_is_not_absent: Literal[True] = True
    residue_reference_validation_required: Literal[True] = True
    labile_modification_handling: LabileModificationHandling
    evidence: ArtifactReference

    @field_validator(
        "higher_is_more_localized",
        "ambiguous_site_sets_preserved",
        "unlocalized_is_not_absent",
        "residue_reference_validation_required",
        mode="before",
    )
    @classmethod
    def booleans_are_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @field_validator("declared_states")
    @classmethod
    def semantic_sets_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return _canonical(values)

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.policy+json"}),
        )

    @model_validator(mode="after")
    def states_are_total(self) -> ModificationLocalizationPolicy:
        if set(self.declared_states) != set(ModificationLocalizationState):
            raise ValueError("localization policy requires all four explicit states")
        return self


class ProteoformQuantificationPolicy(FrozenModel):
    protein_unit: ProteinQuantificationUnit
    transcript_unit: TranscriptQuantificationUnit
    protein_scale: ProteoformQuantificationScale
    transcript_scale: ProteoformQuantificationScale
    zero_is_observed_value: Literal[True] = True
    missing_is_not_zero: Literal[True] = True
    shared_evidence_is_not_allocated: Literal[True] = True
    transcript_protein_mapping_declared: Literal[True] = True
    aggregation_declared: Literal[True] = True
    normalization_declared: Literal[True] = True
    evidence: ArtifactReference

    @field_validator(
        "zero_is_observed_value",
        "missing_is_not_zero",
        "shared_evidence_is_not_allocated",
        "transcript_protein_mapping_declared",
        "aggregation_declared",
        "normalization_declared",
        mode="before",
    )
    @classmethod
    def booleans_are_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.policy+json"}),
        )


class ProteinRnaDiscordanceHandoffRequirements(FrozenModel):
    required_receipt_roles: tuple[ProteinRnaDiscordanceHandoffRole, ...] = Field(
        min_length=M0401_HANDOFF_ROLE_COUNT,
        max_length=M0401_HANDOFF_ROLE_COUNT,
    )
    preserve_isoform_ambiguity: Literal[True] = True
    preserve_site_ambiguity: Literal[True] = True
    preserve_nondetection: Literal[True] = True
    cross_gene_mapping_forbidden: Literal[True] = True
    emit_protein_rna_discordance: Literal[False] = False
    discordance_owner: Literal["downstream_protein_rna_discordance_module"] = (
        "downstream_protein_rna_discordance_module"
    )
    evidence: ArtifactReference

    @field_validator(
        "preserve_isoform_ambiguity",
        "preserve_site_ambiguity",
        "preserve_nondetection",
        "cross_gene_mapping_forbidden",
        "emit_protein_rna_discordance",
        mode="before",
    )
    @classmethod
    def booleans_are_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @field_validator("required_receipt_roles")
    @classmethod
    def roles_are_canonical(
        cls, values: tuple[ProteinRnaDiscordanceHandoffRole, ...]
    ) -> tuple[ProteinRnaDiscordanceHandoffRole, ...]:
        return tuple(sorted(values, key=str))

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.policy+json"}),
        )

    @model_validator(mode="after")
    def roles_are_exact(self) -> ProteinRnaDiscordanceHandoffRequirements:
        if set(self.required_receipt_roles) != set(ProteinRnaDiscordanceHandoffRole):
            raise ValueError("discordance handoff requires every receipt role exactly once")
        return self


class ProteoformProtocolSchema(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion
    applicability: ProteoformApplicability
    assay_protocol_version: SemanticVersion
    specimen_processing_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    required_identity_keys: tuple[ProteoformIdentityKey, ...] = Field(
        min_length=M0401_IDENTITY_KEY_COUNT,
        max_length=M0401_IDENTITY_KEY_COUNT,
    )
    declared_unresolved_states: tuple[ProteoformUnresolvedState, ...] = Field(
        min_length=M0401_UNRESOLVED_STATE_COUNT,
        max_length=M0401_UNRESOLVED_STATE_COUNT,
    )
    reference_bundle: ProteoformReferenceBundle
    coordinate_policy: ProteoformCoordinatePolicy
    evidence_eligibility: ProteoformEvidenceEligibilityPolicy
    isoform_discrimination: IsoformDiscriminationPolicy
    modification_localization: ModificationLocalizationPolicy
    quantification: ProteoformQuantificationPolicy
    discordance_handoff: ProteinRnaDiscordanceHandoffRequirements
    evidence: ArtifactReference

    @field_validator("schema_id")
    @classmethod
    def schema_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("schema", value)

    @field_validator("controlled_vocabulary_id")
    @classmethod
    def vocabulary_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("vocabulary", value)

    @field_validator("required_identity_keys", "declared_unresolved_states")
    @classmethod
    def semantic_sets_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return _canonical(values)

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.policy+json"}),
        )

    @model_validator(mode="after")
    def protocol_declarations_are_total(self) -> ProteoformProtocolSchema:
        if set(self.required_identity_keys) != set(ProteoformIdentityKey):
            raise ValueError("protocol must declare every mandatory proteoform identity key")
        if set(self.declared_unresolved_states) != set(ProteoformUnresolvedState):
            raise ValueError("protocol must distinguish every governed unresolved state")
        evidence = (
            self.evidence_eligibility.evidence,
            self.isoform_discrimination.evidence,
            self.modification_localization.evidence,
            self.quantification.evidence,
            self.discordance_handoff.evidence,
            self.evidence,
        )
        if len({item.digest for item in evidence}) != len(evidence):
            raise ValueError("protocol policy evidence roles require distinct content digests")
        return self


class ApprovedProteoformReferenceBundle(FrozenModel):
    bundle_id: Identifier
    version: SemanticVersion
    bundle_digest: Sha256Digest

    @field_validator("bundle_id")
    @classmethod
    def bundle_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("bundle", value)


class ApprovedControlledVocabulary(FrozenModel):
    vocabulary_id: Identifier
    version: SemanticVersion

    @field_validator("vocabulary_id")
    @classmethod
    def vocabulary_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("vocabulary", value)


class ApprovedCoordinateProfile(FrozenModel):
    genome_convention: CoordinateConvention
    transcript_convention: CoordinateConvention
    protein_convention: CoordinateConvention
    coordinate_mapping_version: SemanticVersion


class ApprovedQuantificationPair(FrozenModel):
    protein_unit: ProteinQuantificationUnit
    transcript_unit: TranscriptQuantificationUnit
    protein_scale: ProteoformQuantificationScale
    transcript_scale: ProteoformQuantificationScale


class ReviewedProteoformConformanceProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    protocol_schema_id: Identifier
    protocol_schema_version: SemanticVersion
    protocol_schema_digest: Sha256Digest
    approved_applicabilities: tuple[ProteoformApplicability, ...] = Field(
        min_length=1, max_length=len(ProteoformApplicability)
    )
    approved_reference_bundles: tuple[ApprovedProteoformReferenceBundle, ...] = Field(
        min_length=1, max_length=M0401_MAX_APPROVED_REFERENCE_BUNDLES
    )
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0401_MAX_APPROVED_VERSIONS
    )
    approved_specimen_processing_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0401_MAX_APPROVED_VERSIONS
    )
    approved_controlled_vocabularies: tuple[ApprovedControlledVocabulary, ...] = Field(
        min_length=1, max_length=M0401_MAX_APPROVED_VERSIONS
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0401_MAX_APPROVED_VERSIONS
    )
    approved_coordinate_profiles: tuple[ApprovedCoordinateProfile, ...] = Field(
        min_length=1, max_length=M0401_MAX_COORDINATE_PROFILES
    )
    approved_quantification_pairs: tuple[ApprovedQuantificationPair, ...] = Field(
        min_length=1, max_length=M0401_MAX_QUANTIFICATION_PAIRS
    )
    approved_evidence_classes: tuple[ProteoformEvidenceClass, ...] = Field(
        min_length=1, max_length=M0401_MAX_EVIDENCE_CLASSES
    )
    approved_labile_modification_handlings: tuple[LabileModificationHandling, ...] = Field(
        min_length=1, max_length=M0401_MAX_LABILE_HANDLINGS
    )
    approved_isoform_discriminators: tuple[ProteoformEvidenceClass, ...] = Field(
        min_length=1, max_length=M0401_MAX_EVIDENCE_CLASSES
    )
    minimum_isoform_discriminators: int = Field(gt=0, le=M0401_MAX_ISOFORM_DISCRIMINATORS)
    minimum_localization_probability_ppm: int = Field(ge=0, le=M0401_RATE_SCALE)
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("profile_id")
    @classmethod
    def profile_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("profile", value)

    @field_validator("protocol_schema_id")
    @classmethod
    def schema_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("schema", value)

    @field_validator("reviewed_by")
    @classmethod
    def reviewer_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("reviewer", value)

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m04-01.profile+json"}),
        )

    @field_validator(
        "approved_applicabilities",
        "approved_reference_bundles",
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabularies",
        "approved_unit_system_versions",
        "approved_coordinate_profiles",
        "approved_quantification_pairs",
        "approved_evidence_classes",
        "approved_labile_modification_handlings",
        "approved_isoform_discriminators",
    )
    @classmethod
    def semantic_sets_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return _canonical(values)

    @model_validator(mode="after")
    def approved_collections_are_unique(self) -> ReviewedProteoformConformanceProfile:
        collections = (
            self.approved_applicabilities,
            self.approved_reference_bundles,
            self.approved_assay_protocol_versions,
            self.approved_specimen_processing_versions,
            self.approved_controlled_vocabularies,
            self.approved_unit_system_versions,
            self.approved_coordinate_profiles,
            self.approved_quantification_pairs,
            self.approved_evidence_classes,
            self.approved_labile_modification_handlings,
            self.approved_isoform_discriminators,
        )
        if any(len(items) != len(set(items)) for items in collections):
            raise ValueError("reviewed profile collections must be unique")
        bundle_ids = tuple(
            (item.bundle_id, item.version) for item in self.approved_reference_bundles
        )
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("approved reference bundle identities must be unique")
        vocab_ids = tuple(
            (item.vocabulary_id, item.version) for item in self.approved_controlled_vocabularies
        )
        if len(vocab_ids) != len(set(vocab_ids)):
            raise ValueError("approved controlled vocabulary identities must be unique")
        return self


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if (
        references.consent.state is not ConsentState.GRANTED
        or references.identity_lineage.state.value != "resolved"
        or any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic)
    ):
        raise ValueError("proteoform protocol evaluation is not authorized")


def _validate_context_opacity(context: ExecutionContext) -> None:
    opaque_proteoform_protocol_identifier("request", context.request_id)
    opaque_proteoform_protocol_identifier("actor", context.actor_id)
    references = context.references
    controls = (
        references.approved_configuration,
        references.identity_lineage,
        references.provenance,
        references.consent,
        references.quality,
        references.support,
        references.intended_use,
    )
    for control in controls:
        opaque_proteoform_protocol_identifier("decision", control.decision_id)
        _owned_artifact(
            control.evidence,
            media_types=frozenset({"application/vnd.glio-proteogen.control+json"}),
        )


class EvaluateProteoformProtocolRequest(FrozenModel):
    operation: Literal["evaluate_proteoform_protocol"] = M0401_OPERATION
    contract_version: Literal["1.0.0"] = M0401_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    protocol_schema: ProteoformProtocolSchema
    conformance_profile: ReviewedProteoformConformanceProfile
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("request_id")
    @classmethod
    def request_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_proteoform_protocol_identifier("request", value)

    @model_validator(mode="after")
    def request_is_authorized_and_pinned(self) -> EvaluateProteoformProtocolRequest:
        _require_authorized_context(self.context)
        _validate_context_opacity(self.context)
        if self.request_id != self.context.request_id:
            raise ValueError("request identifier must equal the authorized context identifier")
        protocol = self.protocol_schema
        profile = self.conformance_profile
        if (
            profile.protocol_schema_id != protocol.schema_id
            or profile.protocol_schema_version != protocol.version
            or profile.protocol_schema_digest != protocol_digest(protocol)
        ):
            raise ValueError("reviewed profile does not pin the supplied proteoform protocol")
        if profile.reviewed_at > self.context.occurred_at:
            raise ValueError("reviewed profile cannot postdate protocol evaluation")
        if self.context.references.approved_configuration.evidence.digest != configuration_digest(
            protocol, profile
        ):
            raise ValueError("approved configuration does not bind proteoform protocol and profile")
        controls = (
            self.context.references.approved_configuration,
            self.context.references.identity_lineage,
            self.context.references.provenance,
            self.context.references.consent,
            self.context.references.quality,
            self.context.references.support,
            self.context.references.intended_use,
        )
        if len({item.evidence.digest for item in controls}) != len(controls):
            raise ValueError("authorization controls require distinct evidence digests")
        protocol_evidence_index(self)
        if len(canonical_json_bytes(self)) > M0401_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M04-01 request exceeds the governed byte cap")
        return self


def _dict_get(value: object, key: str) -> object:
    if type(value) is dict or isinstance(value, dict):
        return dict.get(value, key)
    raise ValueError("authorization preflight requires a strict request object")


def preflight_authorized(value: object) -> None:
    """Check all seven controls without traversing protocol or profile material."""

    if isinstance(value, EvaluateProteoformProtocolRequest):
        _require_authorized_context(value.context)
        return
    context = _dict_get(value, "context")
    if isinstance(context, ExecutionContext):
        _require_authorized_context(context)
        return
    references = _dict_get(context, "references")
    expected = {
        "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
        "identity_lineage": "resolved",
        "provenance": UpstreamDecisionState.ACCEPTED.value,
        "consent": ConsentState.GRANTED.value,
        "quality": UpstreamDecisionState.ACCEPTED.value,
        "support": UpstreamDecisionState.ACCEPTED.value,
        "intended_use": UpstreamDecisionState.ACCEPTED.value,
    }
    try:
        states = {role: _dict_get(_dict_get(references, role), "state") for role in expected}
    except Exception as exc:
        raise ValueError(
            "proteoform protocol evaluation requires accepted upstream controls"
        ) from exc
    if states != expected:
        raise ValueError("proteoform protocol evaluation requires accepted upstream controls")


class ProteoformProtocolConformanceFinding(FrozenModel):
    section: ProteoformProtocolSection
    state: ProteoformProtocolFindingState
    reason_code: Identifier
    remediation_code: Identifier | None = None


_FINDING_VOCABULARY: Final = {
    ProteoformProtocolSection.APPLICABILITY: (
        "applicability_approved",
        "applicability_unapproved",
        "review_applicability",
    ),
    ProteoformProtocolSection.IDENTITY: (
        "identity_keys_complete",
        "identity_keys_incomplete",
        "restore_identity_key_declaration",
    ),
    ProteoformProtocolSection.METADATA_VERSIONS: (
        "metadata_versions_approved",
        "metadata_versions_unapproved",
        "approve_metadata_versions",
    ),
    ProteoformProtocolSection.REFERENCE_BUNDLE: (
        "reference_bundle_approved",
        "reference_bundle_unapproved",
        "approve_reference_bundle",
    ),
    ProteoformProtocolSection.COORDINATE_MAPPING: (
        "coordinate_mapping_approved",
        "coordinate_mapping_incompatible",
        "approve_coordinate_profile",
    ),
    ProteoformProtocolSection.EVIDENCE_ELIGIBILITY: (
        "evidence_eligibility_approved",
        "evidence_eligibility_unapproved",
        "review_evidence_eligibility",
    ),
    ProteoformProtocolSection.ISOFORM_DISCRIMINATION: (
        "isoform_discrimination_approved",
        "isoform_discrimination_unapproved",
        "increase_isoform_discrimination",
    ),
    ProteoformProtocolSection.MODIFICATION_LOCALIZATION: (
        "modification_localization_approved",
        "modification_localization_unapproved",
        "review_localization_policy",
    ),
    ProteoformProtocolSection.QUANTIFICATION: (
        "quantification_units_approved",
        "quantification_units_unapproved",
        "approve_quantification_pair",
    ),
    ProteoformProtocolSection.UNRESOLVED_SEMANTICS: (
        "unresolved_semantics_complete",
        "unresolved_semantics_incomplete",
        "restore_unresolved_state_semantics",
    ),
    ProteoformProtocolSection.DISCORDANCE_HANDOFF: (
        "discordance_handoff_closed",
        "discordance_handoff_unsafe",
        "restore_discordance_handoff_boundary",
    ),
}


def _finding(
    section: ProteoformProtocolSection,
    *,
    passed: bool,
) -> ProteoformProtocolConformanceFinding:
    success, failure, remediation = _FINDING_VOCABULARY[section]
    return ProteoformProtocolConformanceFinding(
        section=section,
        state=(
            ProteoformProtocolFindingState.PASS if passed else ProteoformProtocolFindingState.FAIL
        ),
        reason_code=success if passed else failure,
        remediation_code=None if passed else remediation,
    )


def expected_protocol_findings(
    protocol: ProteoformProtocolSchema,
    profile: ReviewedProteoformConformanceProfile,
) -> tuple[ProteoformProtocolConformanceFinding, ...]:
    """Derive the exact eleven reviewed-domain findings."""

    bundle = protocol.reference_bundle
    approved_bundle = ApprovedProteoformReferenceBundle(
        bundle_id=bundle.bundle_id,
        version=bundle.version,
        bundle_digest=reference_bundle_digest(bundle),
    )
    vocabulary = ApprovedControlledVocabulary(
        vocabulary_id=protocol.controlled_vocabulary_id,
        version=protocol.controlled_vocabulary_version,
    )
    coordinate = ApprovedCoordinateProfile(
        genome_convention=protocol.coordinate_policy.genome_convention,
        transcript_convention=protocol.coordinate_policy.transcript_convention,
        protein_convention=protocol.coordinate_policy.protein_convention,
        coordinate_mapping_version=protocol.coordinate_policy.coordinate_mapping_version,
    )
    quantification = ApprovedQuantificationPair(
        protein_unit=protocol.quantification.protein_unit,
        transcript_unit=protocol.quantification.transcript_unit,
        protein_scale=protocol.quantification.protein_scale,
        transcript_scale=protocol.quantification.transcript_scale,
    )
    return (
        _finding(
            ProteoformProtocolSection.APPLICABILITY,
            passed=protocol.applicability in profile.approved_applicabilities,
        ),
        _finding(
            ProteoformProtocolSection.IDENTITY,
            passed=set(protocol.required_identity_keys) == set(ProteoformIdentityKey),
        ),
        _finding(
            ProteoformProtocolSection.METADATA_VERSIONS,
            passed=(
                protocol.assay_protocol_version in profile.approved_assay_protocol_versions
                and protocol.specimen_processing_version
                in profile.approved_specimen_processing_versions
                and vocabulary in profile.approved_controlled_vocabularies
                and protocol.unit_system_version in profile.approved_unit_system_versions
            ),
        ),
        _finding(
            ProteoformProtocolSection.REFERENCE_BUNDLE,
            passed=approved_bundle in profile.approved_reference_bundles,
        ),
        _finding(
            ProteoformProtocolSection.COORDINATE_MAPPING,
            passed=coordinate in profile.approved_coordinate_profiles,
        ),
        _finding(
            ProteoformProtocolSection.EVIDENCE_ELIGIBILITY,
            passed=set(protocol.evidence_eligibility.eligible_evidence_classes).issubset(
                profile.approved_evidence_classes
            )
            and (
                (
                    protocol.applicability is ProteoformApplicability.TOP_DOWN
                    and ProteoformEvidenceClass.INTACT_PROTEOFORM
                    in protocol.evidence_eligibility.eligible_evidence_classes
                )
                or (
                    protocol.applicability is not ProteoformApplicability.TOP_DOWN
                    and bool(
                        set(protocol.evidence_eligibility.eligible_evidence_classes)
                        & {
                            ProteoformEvidenceClass.ISOFORM_UNIQUE_PEPTIDE,
                            ProteoformEvidenceClass.SPLICE_JUNCTION_PEPTIDE,
                            ProteoformEvidenceClass.SEQUENCE_VARIANT_PEPTIDE,
                            ProteoformEvidenceClass.TERMINAL_PEPTIDE,
                        }
                    )
                )
            ),
        ),
        _finding(
            ProteoformProtocolSection.ISOFORM_DISCRIMINATION,
            passed=set(protocol.isoform_discrimination.accepted_discriminators).issubset(
                profile.approved_isoform_discriminators
            )
            and protocol.isoform_discrimination.minimum_independent_discriminators
            >= profile.minimum_isoform_discriminators,
        ),
        _finding(
            ProteoformProtocolSection.MODIFICATION_LOCALIZATION,
            passed=(
                protocol.modification_localization.labile_modification_handling
                in profile.approved_labile_modification_handlings
            )
            and protocol.modification_localization.minimum_localized_probability_ppm
            >= profile.minimum_localization_probability_ppm,
        ),
        _finding(
            ProteoformProtocolSection.QUANTIFICATION,
            passed=quantification in profile.approved_quantification_pairs,
        ),
        _finding(
            ProteoformProtocolSection.UNRESOLVED_SEMANTICS,
            passed=set(protocol.declared_unresolved_states) == set(ProteoformUnresolvedState),
        ),
        _finding(
            ProteoformProtocolSection.DISCORDANCE_HANDOFF,
            passed=set(protocol.discordance_handoff.required_receipt_roles)
            == set(ProteinRnaDiscordanceHandoffRole),
        ),
    )


class ProteoformProtocolSectionReceipt(FrozenModel):
    section: ProteoformProtocolSection
    section_digest: Sha256Digest
    state: ProteoformProtocolFindingState


class ProteoformProtocolReceipt(FrozenModel):
    protocol_digest: Sha256Digest
    profile_digest: Sha256Digest
    configuration_digest: Sha256Digest
    reference_bundle_digest: Sha256Digest
    coordinate_policy_digest: Sha256Digest
    sections: tuple[ProteoformProtocolSectionReceipt, ...] = Field(
        min_length=M0401_SECTION_COUNT, max_length=M0401_SECTION_COUNT
    )
    identity_subject_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    parent_target: Literal["protein_rna_discordance"] = M0401_PARENT_TARGET
    disposition: ProteoformProtocolConformanceDisposition
    receipt_digest: Sha256Digest

    @field_validator("sections")
    @classmethod
    def sections_are_canonical(
        cls, values: tuple[ProteoformProtocolSectionReceipt, ...]
    ) -> tuple[ProteoformProtocolSectionReceipt, ...]:
        return tuple(sorted(values, key=lambda item: _PROTOCOL_SECTION_ORDER[item.section]))

    @model_validator(mode="after")
    def receipt_is_structurally_closed(self) -> ProteoformProtocolReceipt:
        sections = tuple(item.section for item in self.sections)
        if len(sections) != len(set(sections)) or set(sections) != set(ProteoformProtocolSection):
            raise ValueError("protocol receipt requires every section exactly once")
        any_failure = any(
            item.state is ProteoformProtocolFindingState.FAIL for item in self.sections
        )
        expected_disposition = (
            ProteoformProtocolConformanceDisposition.QUARANTINED
            if any_failure
            else ProteoformProtocolConformanceDisposition.CONFORMANT
        )
        if self.disposition is not expected_disposition:
            raise ValueError("protocol receipt disposition contradicts section states")
        if self.receipt_digest != receipt_digest(self):
            raise ValueError("protocol receipt digest does not match its canonical content")
        return self


def expected_protocol_receipt(
    request: EvaluateProteoformProtocolRequest,
) -> ProteoformProtocolReceipt:
    findings = expected_protocol_findings(request.protocol_schema, request.conformance_profile)
    disposition = (
        ProteoformProtocolConformanceDisposition.QUARANTINED
        if any(item.state is ProteoformProtocolFindingState.FAIL for item in findings)
        else ProteoformProtocolConformanceDisposition.CONFORMANT
    )
    references = request.context.references
    payload: dict[str, object] = {
        "protocol_digest": protocol_digest(request.protocol_schema),
        "profile_digest": profile_digest(request.conformance_profile),
        "configuration_digest": configuration_digest(
            request.protocol_schema, request.conformance_profile
        ),
        "reference_bundle_digest": reference_bundle_digest(
            request.protocol_schema.reference_bundle
        ),
        "coordinate_policy_digest": coordinate_policy_digest(
            request.protocol_schema.coordinate_policy
        ),
        "sections": tuple(
            ProteoformProtocolSectionReceipt(
                section=finding.section,
                section_digest=protocol_section_digest(
                    request.protocol_schema, finding.section.value
                ),
                state=finding.state,
            )
            for finding in findings
        ),
        "identity_subject_digest": references.identity_lineage.binding_digest,
        "intended_use_evidence_digest": references.intended_use.evidence.digest,
        "parent_target": M0401_PARENT_TARGET,
        "disposition": disposition,
        "receipt_digest": "sha256:" + ("1" * 64),
    }
    payload["receipt_digest"] = receipt_digest(payload)
    return ProteoformProtocolReceipt.model_validate(payload, strict=True)


def protocol_evidence_index(
    request: EvaluateProteoformProtocolRequest,
) -> tuple[EvidenceReference, ...]:
    """Return the exact 21-item, privacy-minimized evidence index."""

    references = request.context.references
    protocol = request.protocol_schema
    bundle = protocol.reference_bundle
    artifacts = (
        references.approved_configuration.evidence,
        references.identity_lineage.evidence,
        references.provenance.evidence,
        references.consent.evidence,
        references.quality.evidence,
        references.support.evidence,
        references.intended_use.evidence,
        bundle.genome_reference,
        bundle.transcript_annotation_reference,
        bundle.canonical_protein_reference,
        bundle.isoform_reference,
        bundle.transcript_protein_mapping_reference,
        bundle.modification_vocabulary_reference,
        bundle.bundle_manifest_reference,
        protocol.evidence_eligibility.evidence,
        protocol.isoform_discrimination.evidence,
        protocol.modification_localization.evidence,
        protocol.quantification.evidence,
        protocol.discordance_handoff.evidence,
        protocol.evidence,
        request.conformance_profile.evidence,
    )
    if (
        len(artifacts) != M0401_EVIDENCE_COUNT
        or len({item.artifact_id for item in artifacts}) != M0401_EVIDENCE_COUNT
        or len({item.digest for item in artifacts}) != M0401_EVIDENCE_COUNT
    ):
        raise ValueError("M04-01 requires exactly 21 distinct evidence artifacts and digests")
    return tuple(
        sorted(
            (
                EvidenceReference(
                    reference=item,
                    role="evidence",
                    claim="Caller-declared content-addressed M04-01 protocol evidence.",
                )
                for item in artifacts
            ),
            key=canonical_json_bytes,
        )
    )


def expected_support(
    disposition: ProteoformProtocolConformanceDisposition,
) -> SupportDecision:
    if disposition is ProteoformProtocolConformanceDisposition.CONFORMANT:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="proteoform_protocol_conformant",
            rationale=M0401_CONFORMANT_SUPPORT_RATIONALE,
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="proteoform_protocol_quarantined",
        rationale=M0401_QUARANTINED_SUPPORT_RATIONALE,
    )


def expected_uncertainty() -> UncertaintyProfile:
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0401_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=tuple(sorted(M0401_SENSITIVITY_NOTES)),
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code="proteoform_protocol_conformance_only",
                    statement=(
                        "This result validates declared proteoform protocol metadata only; it "
                        "does not inspect signals or perform scientific inference."
                    ),
                ),
                Limitation(
                    code="external_reference_authority_unverified",
                    statement=(
                        "Reference, configuration, control, and review authorities remain "
                        "caller-declared and are not authenticated by M04-01."
                    ),
                ),
                Limitation(
                    code="protein_rna_discordance_not_inferred",
                    statement=(
                        "The handoff preserves metadata and unresolved states only; no "
                        "protein-RNA discordance, proteotype, subtype, kinase, or treatment "
                        "claim is produced."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def _control_decisions(
    request: EvaluateProteoformProtocolRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    records = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return tuple(sorted(records, key=canonical_json_bytes))


def expected_provenance(
    request: EvaluateProteoformProtocolRequest,
    receipt: ProteoformProtocolReceipt | None = None,
) -> ProvenanceRecord:
    active_receipt = receipt if receipt is not None else expected_protocol_receipt(request)
    request_hash = canonical_request_digest(request)
    evidence = protocol_evidence_index(request)
    input_digests = {
        request_hash,
        protocol_digest(request.protocol_schema),
        profile_digest(request.conformance_profile),
        configuration_digest(request.protocol_schema, request.conformance_profile),
        reference_bundle_digest(request.protocol_schema.reference_bundle),
        coordinate_policy_digest(request.protocol_schema.coordinate_policy),
        active_receipt.receipt_digest,
        *(item.section_digest for item in active_receipt.sections),
        *(item.reference.digest for item in evidence),
    }
    if request.supersedes_result_digest is not None:
        input_digests.add(request.supersedes_result_digest)
    references = request.context.references
    suffix = request_hash.removeprefix("sha256:")
    return ProvenanceRecord(
        activity_id=f"activity.m0401.{suffix}",
        actor_id=request.context.actor_id,
        module_id=M0401_MODULE_ID,
        module_version=M0401_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(input_digests)),
        configuration_digest=configuration_digest(
            request.protocol_schema, request.conformance_profile
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


class ProteoformProtocolConformanceResult(FrozenModel):
    output_type: Literal["proteoform_protocol_conformance_result"] = (
        "proteoform_protocol_conformance_result"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0401_CONTRACT_VERSION
    request_digest: Sha256Digest
    protocol_digest: Sha256Digest
    profile_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateProteoformProtocolRequest
    receipt: ProteoformProtocolReceipt
    findings: tuple[ProteoformProtocolConformanceFinding, ...] = Field(
        min_length=M0401_SECTION_COUNT, max_length=M0401_SECTION_COUNT
    )
    status: ProteoformProtocolConformanceStatus
    disposition: ProteoformProtocolConformanceDisposition
    parent_target: Literal["protein_rna_discordance"] = M0401_PARENT_TARGET
    emits_protein_rna_discordance: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_proteoform_or_isoform: Literal[False] = False
    localizes_modification: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream_evidence: Literal[False] = False
    infers_identity_or_consent: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=M0401_EVIDENCE_COUNT, max_length=M0401_EVIDENCE_COUNT
    )
    limitations: tuple[Limitation, ...] = Field(
        min_length=M0401_LIMITATION_COUNT, max_length=M0401_LIMITATION_COUNT
    )
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator(
        "emits_protein_rna_discordance",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "infers_proteoform_or_isoform",
        "localizes_modification",
        "infers_kinase_activity",
        "performs_all_omics_fusion",
        "recommends_treatment",
        "mutates_upstream_evidence",
        "infers_identity_or_consent",
        "human_review_required",
        mode="before",
    )
    @classmethod
    def booleans_are_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @field_validator("findings")
    @classmethod
    def findings_are_in_protocol_order(
        cls, values: tuple[ProteoformProtocolConformanceFinding, ...]
    ) -> tuple[ProteoformProtocolConformanceFinding, ...]:
        return tuple(sorted(values, key=lambda item: _PROTOCOL_SECTION_ORDER[item.section]))

    @field_validator("evidence", "limitations")
    @classmethod
    def semantic_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return _canonical(values)

    @field_validator("uncertainty")
    @classmethod
    def uncertainty_is_canonical(cls, value: UncertaintyProfile) -> UncertaintyProfile:
        return value.model_copy(
            update={"sensitivity_notes": tuple(sorted(value.sensitivity_notes))}
        )

    @field_validator("provenance")
    @classmethod
    def provenance_is_canonical(cls, value: ProvenanceRecord) -> ProvenanceRecord:
        return value.model_copy(
            update={
                "input_digests": tuple(sorted(value.input_digests)),
                "control_decisions": tuple(
                    sorted(value.control_decisions, key=canonical_json_bytes)
                ),
            }
        )

    @model_validator(mode="after")
    def result_is_exact_replay(self) -> ProteoformProtocolConformanceResult:
        request_hash = canonical_request_digest(self.request)
        protocol_hash = protocol_digest(self.request.protocol_schema)
        profile_hash = profile_digest(self.request.conformance_profile)
        config_hash = configuration_digest(
            self.request.protocol_schema, self.request.conformance_profile
        )
        suffix = request_hash.removeprefix("sha256:")
        if (
            self.result_id != f"result.m0401.{suffix}"
            or self.request_digest != request_hash
            or self.protocol_digest != protocol_hash
            or self.profile_digest != profile_hash
            or self.configuration_digest != config_hash
        ):
            raise ValueError("result identifiers and protocol bindings are inconsistent")
        expected_receipt = expected_protocol_receipt(self.request)
        if self.receipt != expected_receipt:
            raise ValueError("result receipt contradicts the embedded request")
        findings = expected_protocol_findings(
            self.request.protocol_schema, self.request.conformance_profile
        )
        if self.findings != findings:
            raise ValueError("result findings contradict the embedded request")
        any_failure = any(item.state is ProteoformProtocolFindingState.FAIL for item in findings)
        expected_status = (
            ProteoformProtocolConformanceStatus.NONCONFORMANT
            if any_failure
            else ProteoformProtocolConformanceStatus.CONFORMANT
        )
        expected_disposition = (
            ProteoformProtocolConformanceDisposition.QUARANTINED
            if any_failure
            else ProteoformProtocolConformanceDisposition.CONFORMANT
        )
        if (
            self.status is not expected_status
            or self.disposition is not expected_disposition
            or self.support != expected_support(expected_disposition)
            or self.human_review_required is not any_failure
        ):
            raise ValueError("result disposition and support envelope contradicts findings")
        if self.uncertainty != expected_uncertainty():
            raise ValueError("result uncertainty exceeds the M04-01 declaration boundary")
        if self.provenance != expected_provenance(self.request, expected_receipt):
            raise ValueError("result provenance contradicts the embedded request")
        if self.evidence != protocol_evidence_index(self.request):
            raise ValueError("result evidence index contradicts the embedded request")
        if self.limitations != expected_limitations():
            raise ValueError("result limitations exceed the M04-01 authority boundary")
        if self.completed_at != self.request.context.occurred_at:
            raise ValueError("result completion time must equal the authorized execution time")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match its canonical content")
        return self


__all__ = [
    "M0401_CONFORMANT_SUPPORT_RATIONALE",
    "M0401_CONTRACT_VERSION",
    "M0401_EVIDENCE_COUNT",
    "M0401_HANDOFF_ROLE_COUNT",
    "M0401_IDENTITY_KEY_COUNT",
    "M0401_LIMITATION_COUNT",
    "M0401_MAX_APPROVED_REFERENCE_BUNDLES",
    "M0401_MAX_APPROVED_VERSIONS",
    "M0401_MAX_CANONICAL_PROTEIN_SEQUENCES",
    "M0401_MAX_CANONICAL_REQUEST_BYTES",
    "M0401_MAX_COORDINATE_PROFILES",
    "M0401_MAX_EVIDENCE_CLASSES",
    "M0401_MAX_GENE_RECORDS",
    "M0401_MAX_ISOFORM_DISCRIMINATORS",
    "M0401_MAX_ISOFORM_SEQUENCES",
    "M0401_MAX_LABILE_HANDLINGS",
    "M0401_MAX_MODIFICATION_TERMS",
    "M0401_MAX_QUANTIFICATION_PAIRS",
    "M0401_MAX_TRANSCRIPT_PROTEIN_EDGES",
    "M0401_MAX_TRANSCRIPT_RECORDS",
    "M0401_MODULE_ID",
    "M0401_OPERATION",
    "M0401_PARENT_TARGET",
    "M0401_QUARANTINED_SUPPORT_RATIONALE",
    "M0401_RATE_SCALE",
    "M0401_SECTION_COUNT",
    "M0401_SENSITIVITY_NOTES",
    "M0401_UNCERTAINTY_RATIONALES",
    "M0401_UNRESOLVED_STATE_COUNT",
    "ApprovedControlledVocabulary",
    "ApprovedCoordinateProfile",
    "ApprovedProteoformReferenceBundle",
    "ApprovedQuantificationPair",
    "CoordinateConvention",
    "EvaluateProteoformProtocolRequest",
    "IsoformDiscriminationPolicy",
    "LabileModificationHandling",
    "ModificationLocalizationPolicy",
    "ModificationLocalizationState",
    "ProteinQuantificationUnit",
    "ProteinQuantityUnit",
    "ProteinRnaDiscordanceHandoffRequirements",
    "ProteinRnaDiscordanceHandoffRole",
    "ProteoformApplicability",
    "ProteoformAssayApplicability",
    "ProteoformCoordinatePolicy",
    "ProteoformEvidenceClass",
    "ProteoformEvidenceEligibilityPolicy",
    "ProteoformIdentityKey",
    "ProteoformLocalizationState",
    "ProteoformProtocolConformanceDisposition",
    "ProteoformProtocolConformanceFinding",
    "ProteoformProtocolConformanceResult",
    "ProteoformProtocolConformanceStatus",
    "ProteoformProtocolFindingState",
    "ProteoformProtocolOpaqueNamespace",
    "ProteoformProtocolReceipt",
    "ProteoformProtocolSchema",
    "ProteoformProtocolSection",
    "ProteoformProtocolSectionReceipt",
    "ProteoformQuantificationPolicy",
    "ProteoformQuantificationScale",
    "ProteoformReferenceBundle",
    "ProteoformReferenceCardinality",
    "ProteoformUnresolvedState",
    "QuantityScale",
    "ReviewedProteoformConformanceProfile",
    "TranscriptQuantificationUnit",
    "TranscriptQuantityUnit",
    "expected_limitations",
    "expected_protocol_findings",
    "expected_protocol_receipt",
    "expected_provenance",
    "expected_support",
    "expected_uncertainty",
    "opaque_proteoform_protocol_identifier",
    "preflight_authorized",
    "protocol_evidence_index",
]
