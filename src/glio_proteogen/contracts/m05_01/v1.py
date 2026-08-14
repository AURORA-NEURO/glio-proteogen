"""Strict public contracts for M05-01 PTM-localization protocol conformance."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, Literal, cast

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m05_01.canonical import (
    assay_specimen_policy_digest,
    canonical_request_digest,
    configuration_digest,
    profile_digest,
    protocol_digest,
    receipt_digest,
    reference_bundle_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
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
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0501_MODULE_ID: Final = "GLIO-PROTEOGEN-M05-01"
M0501_OPERATION: Final = "evaluate_ptm_localization_protocol"
M0501_CONTRACT_VERSION: Final = "1.0.0"
M0501_PARENT_TARGET: Final = "variant_peptide"
M0501_OWNER: Final = "Quality engineering"
M0501_SAFETY_CLASS: Final = "S2"
M0501_GATE: Final = "G0"
M0501_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0501_MAX_APPROVED_REFERENCE_BUNDLES: Final = 32
M0501_MAX_APPROVED_VERSIONS: Final = 16
M0501_MAX_METADATA_FIELDS: Final = 8
M0501_MAX_COMPATIBILITY_RULES: Final = 32
M0501_MAX_VOCABULARY_TERMS: Final = 12
M0501_MAX_UNIT_POLICIES: Final = 6
M0501_IDENTITY_KEY_COUNT: Final = 7
M0501_UNRESOLVED_STATE_COUNT: Final = 10
M0501_SECTION_COUNT: Final = 8
M0501_INPUT_ROLE_COUNT: Final = 3
M0501_EVIDENCE_COUNT: Final = 15
M0501_LIMITATION_COUNT: Final = 3

_OWNED_MEDIA_TYPES: Final = frozenset(
    {
        "application/vnd.glio-proteogen.control+json",
        "application/vnd.glio-proteogen.m05-01.reference+json",
        "application/vnd.glio-proteogen.m05-01.reference-manifest+json",
        "application/vnd.glio-proteogen.m05-01.policy+json",
        "application/vnd.glio-proteogen.m05-01.profile+json",
    }
)
_LOWERCASE_MEDIA_TYPE: Final = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
_OPAQUE_IDENTIFIER: Final = re.compile(
    r"^(?:request|actor|decision|schema|profile|bundle|vocabulary|term|unit|field|rule|policy|reviewer|evidence)\.[0-9a-f]{64}$"
    r"|^(?:result|finding|activity)\.m0501\.[0-9a-f]{64}$"
)


class PtmLocalizationProtocolOpaqueNamespace(StrEnum):
    REQUEST = "request"
    ACTOR = "actor"
    DECISION = "decision"
    SCHEMA = "schema"
    PROFILE = "profile"
    BUNDLE = "bundle"
    VOCABULARY = "vocabulary"
    TERM = "term"
    UNIT = "unit"
    FIELD = "field"
    RULE = "rule"
    POLICY = "policy"
    REVIEWER = "reviewer"
    EVIDENCE = "evidence"
    RESULT = "result.m0501"
    FINDING = "finding.m0501"
    ACTIVITY = "activity.m0501"


def opaque_ptm_localization_protocol_identifier(
    namespace: PtmLocalizationProtocolOpaqueNamespace | str,
    value: str,
) -> Identifier:
    """Require an opaque digest alias in the field-owned namespace."""

    prefix = (
        namespace.value
        if isinstance(namespace, PtmLocalizationProtocolOpaqueNamespace)
        else namespace
    )
    if not value.startswith(f"{prefix}.") or _OPAQUE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"identifier must be an opaque {prefix} digest alias")
    return value


def _strict_bool(value: object) -> object:
    if type(value) is not bool:
        raise ValueError("boolean values must be exact booleans")
    return value


def _canonical[T](values: tuple[T, ...]) -> tuple[T, ...]:
    if len(values) != len(set(values)):
        raise ValueError("semantic collection values must be unique")
    return tuple(sorted(values, key=canonical_json_bytes))


def _owned_artifact(
    value: ArtifactReference,
    *,
    media_types: frozenset[str] = _OWNED_MEDIA_TYPES,
) -> ArtifactReference:
    opaque_ptm_localization_protocol_identifier("evidence", value.artifact_id)
    if value.artifact_id != f"evidence.{value.digest.removeprefix('sha256:')}":
        raise ValueError("M05-01 evidence identity must equal its content digest alias")
    if (
        _LOWERCASE_MEDIA_TYPE.fullmatch(value.media_type) is None
        or value.media_type not in media_types
    ):
        raise ValueError("M05-01 evidence media type is not owned or allowlisted")
    return value


class PtmLocalizationInputRole(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"


class PtmLocalizationIdentityKey(StrEnum):
    PATIENT = "patient_id"
    SPECIMEN = "specimen_id"
    ALIQUOT = "aliquot_id"
    SECTION = "section_id"
    ANALYTE = "analyte_id"
    RUN = "run_id"
    DERIVED_OBJECT = "derived_object_id"


class PtmLocalizationUnresolvedState(StrEnum):
    MISSING = "missing"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"
    REDACTED = "redacted"
    NOT_DETECTED = "not_detected"
    BELOW_DETECTION_LIMIT = "below_detection_limit"
    VARIANT_AMBIGUOUS = "variant_ambiguous"
    SITE_AMBIGUOUS = "site_ambiguous"


class PtmLocalizationUnresolvedAction(StrEnum):
    PRESERVE = "preserve"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


_EXPECTED_UNRESOLVED_ACTION: Final = {
    PtmLocalizationUnresolvedState.MISSING: PtmLocalizationUnresolvedAction.QUARANTINE,
    PtmLocalizationUnresolvedState.UNKNOWN: PtmLocalizationUnresolvedAction.QUARANTINE,
    PtmLocalizationUnresolvedState.UNSUPPORTED: PtmLocalizationUnresolvedAction.ABSTAIN,
    PtmLocalizationUnresolvedState.CONFLICTING: PtmLocalizationUnresolvedAction.QUARANTINE,
    PtmLocalizationUnresolvedState.NOT_APPLICABLE: PtmLocalizationUnresolvedAction.PRESERVE,
    PtmLocalizationUnresolvedState.REDACTED: PtmLocalizationUnresolvedAction.QUARANTINE,
    PtmLocalizationUnresolvedState.NOT_DETECTED: PtmLocalizationUnresolvedAction.PRESERVE,
    PtmLocalizationUnresolvedState.BELOW_DETECTION_LIMIT: PtmLocalizationUnresolvedAction.PRESERVE,
    PtmLocalizationUnresolvedState.VARIANT_AMBIGUOUS: PtmLocalizationUnresolvedAction.QUARANTINE,
    PtmLocalizationUnresolvedState.SITE_AMBIGUOUS: PtmLocalizationUnresolvedAction.QUARANTINE,
}


class PtmLocalizationVocabularyMeaning(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"
    REDACTED = "redacted"
    NOT_DETECTED = "not_detected"
    BELOW_DETECTION_LIMIT = "below_detection_limit"
    VARIANT_AMBIGUOUS = "variant_ambiguous"
    SITE_AMBIGUOUS = "site_ambiguous"
    UNLOCALIZED = "unlocalized"


class PtmLocalizationQuantity(StrEnum):
    MASS = "mass"
    MASS_TO_CHARGE = "mass_to_charge"
    RETENTION_TIME = "retention_time"
    MASS_ERROR = "mass_error"
    LOCALIZATION_CONFIDENCE = "localization_confidence"
    CARDINALITY = "cardinality"


class PtmLocalizationUnit(StrEnum):
    DALTON = "dalton"
    THOMSON = "thomson"
    MINUTE = "minute"
    PARTS_PER_MILLION = "parts_per_million"
    PROBABILITY_PPM = "probability_ppm"
    COUNT = "count"


_EXPECTED_UNIT: Final = {
    PtmLocalizationQuantity.MASS: PtmLocalizationUnit.DALTON,
    PtmLocalizationQuantity.MASS_TO_CHARGE: PtmLocalizationUnit.THOMSON,
    PtmLocalizationQuantity.RETENTION_TIME: PtmLocalizationUnit.MINUTE,
    PtmLocalizationQuantity.MASS_ERROR: PtmLocalizationUnit.PARTS_PER_MILLION,
    PtmLocalizationQuantity.LOCALIZATION_CONFIDENCE: PtmLocalizationUnit.PROBABILITY_PPM,
    PtmLocalizationQuantity.CARDINALITY: PtmLocalizationUnit.COUNT,
}


class PtmLocalizationMetadataFieldName(StrEnum):
    ASSAY_PROTOCOL_VERSION = "assay_protocol_version"
    SPECIMEN_PROCESSING_VERSION = "specimen_processing_version"
    CONTROLLED_VOCABULARY_VERSION = "controlled_vocabulary_version"
    UNIT_SYSTEM_VERSION = "unit_system_version"
    REFERENCE_BUNDLE_VERSION = "reference_bundle_version"
    IDENTITY_KEYS = "identity_keys"
    UNRESOLVED_STATE = "unresolved_state"
    PARENT_TARGET = "parent_target"


class PtmLocalizationCompatibilityDimension(StrEnum):
    ASSAY = "assay"
    SPECIMEN = "specimen"
    VOCABULARY = "vocabulary"
    UNIT_SYSTEM = "unit_system"
    PARENT_TARGET = "parent_target"


class PtmLocalizationCompatibilityState(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNREVIEWED = "unreviewed"


class PtmLocalizationAssayKind(StrEnum):
    DATA_DEPENDENT_ACQUISITION = "data_dependent_acquisition"
    DATA_INDEPENDENT_ACQUISITION = "data_independent_acquisition"
    TARGETED_MASS_SPECTROMETRY = "targeted_mass_spectrometry"


class PtmLocalizationSpecimenKind(StrEnum):
    TISSUE = "tissue"
    CELL_MODEL = "cell_model"
    BIOFLUID = "biofluid"


class PtmLocalizationSupportDomain(StrEnum):
    REVIEWED_SUPPORTED = "reviewed_supported"
    NOVEL_OOD = "novel_ood"
    UNRESOLVED = "unresolved"


class VariantPeptideHandoffRole(StrEnum):
    PROTOCOL_RECEIPT = "protocol_receipt"
    IDENTITY_BINDING = "identity_binding"
    REFERENCE_BUNDLE = "reference_bundle"
    UNIT_DECLARATIONS = "unit_declarations"
    UNRESOLVED_SEMANTICS = "unresolved_semantics"
    PROVENANCE = "provenance"


class PtmLocalizationProtocolSection(StrEnum):
    IDENTITY = "identity"
    VERSIONS = "versions"
    UNITS = "units"
    COMPLETENESS = "completeness"
    ASSAY_SUPPORT = "assay_support"
    PARENT_QUALITY = "parent_quality"
    COMPATIBILITY = "compatibility"
    UNRESOLVED_SEMANTICS = "unresolved_semantics"


_SECTION_ORDER: Final = {
    section: index for index, section in enumerate(PtmLocalizationProtocolSection)
}


class PtmLocalizationProtocolFindingState(StrEnum):
    PASS = "pass"  # noqa: S105 - conformance state, not a secret.
    FAIL = "fail"
    INDETERMINATE = "indeterminate"


class PtmLocalizationProtocolConformanceStatus(StrEnum):
    CONFORMANT = "conformant"
    NONCONFORMANT = "nonconformant"
    INDETERMINATE = "indeterminate"


class PtmLocalizationProtocolConformanceDisposition(StrEnum):
    CONFORMANT = "conformant"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class PtmLocalizationInputReference(FrozenModel):
    role: PtmLocalizationInputRole
    reference: ArtifactReference

    @field_validator("reference")
    @classmethod
    def reference_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m05-01.reference+json"}),
        )


class PtmLocalizationReferenceCardinality(FrozenModel):
    mass_spectrometry_proteome: Literal[1] = 1
    genome_transcriptome: Literal[1] = 1
    ptm_annotations: Literal[1] = 1


class PtmLocalizationReferenceBundle(FrozenModel):
    bundle_id: Identifier
    version: SemanticVersion
    cardinality: PtmLocalizationReferenceCardinality
    references: tuple[PtmLocalizationInputReference, ...] = Field(
        min_length=M0501_INPUT_ROLE_COUNT,
        max_length=M0501_INPUT_ROLE_COUNT,
    )
    manifest_reference: ArtifactReference

    @field_validator("bundle_id")
    @classmethod
    def bundle_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("bundle", value)

    @field_validator("references")
    @classmethod
    def references_are_canonical(
        cls, values: tuple[PtmLocalizationInputReference, ...]
    ) -> tuple[PtmLocalizationInputReference, ...]:
        return tuple(_canonical(values))

    @field_validator("manifest_reference")
    @classmethod
    def manifest_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset(
                {"application/vnd.glio-proteogen.m05-01.reference-manifest+json"}
            ),
        )

    @model_validator(mode="after")
    def roles_are_exact(self) -> PtmLocalizationReferenceBundle:
        if {item.role for item in self.references} != set(PtmLocalizationInputRole):
            raise ValueError("reference bundle requires every scientific input role exactly once")
        artifacts = (*tuple(item.reference for item in self.references), self.manifest_reference)
        if len({item.artifact_id for item in artifacts}) != len(artifacts) or len(
            {item.digest for item in artifacts}
        ) != len(artifacts):
            raise ValueError("reference bundle artifacts and digests must be distinct")
        return self


class PtmLocalizationVocabularyTerm(FrozenModel):
    term_id: Identifier
    meaning: PtmLocalizationVocabularyMeaning

    @field_validator("term_id")
    @classmethod
    def term_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("term", value)


class PtmLocalizationControlledVocabulary(FrozenModel):
    vocabulary_id: Identifier
    version: SemanticVersion
    terms: tuple[PtmLocalizationVocabularyTerm, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_VOCABULARY_TERMS,
    )

    @field_validator("vocabulary_id")
    @classmethod
    def vocabulary_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("vocabulary", value)

    @field_validator("terms")
    @classmethod
    def terms_are_canonical(
        cls, values: tuple[PtmLocalizationVocabularyTerm, ...]
    ) -> tuple[PtmLocalizationVocabularyTerm, ...]:
        canonical = tuple(_canonical(values))
        if len({item.term_id for item in canonical}) != len(canonical) or len(
            {item.meaning for item in canonical}
        ) != len(canonical):
            raise ValueError("controlled vocabulary term identifiers and meanings must be unique")
        return canonical


class PtmLocalizationUnitPolicy(FrozenModel):
    unit_policy_id: Identifier
    version: SemanticVersion
    quantity: PtmLocalizationQuantity
    unit: PtmLocalizationUnit

    @field_validator("unit_policy_id")
    @classmethod
    def unit_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("unit", value)


class PtmLocalizationMetadataFieldPolicy(FrozenModel):
    field_policy_id: Identifier
    field_name: PtmLocalizationMetadataFieldName
    required: bool
    minimum_cardinality: int = Field(ge=1, le=1)
    maximum_cardinality: int = Field(ge=1, le=1)

    @field_validator("field_policy_id")
    @classmethod
    def field_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("field", value)

    @field_validator("required", mode="before")
    @classmethod
    def required_is_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @model_validator(mode="after")
    def cardinality_is_ordered(self) -> PtmLocalizationMetadataFieldPolicy:
        if self.minimum_cardinality > self.maximum_cardinality:
            raise ValueError("metadata cardinality minimum cannot exceed maximum")
        return self


class PtmLocalizationCompatibilityRule(FrozenModel):
    rule_id: Identifier
    left_dimension: PtmLocalizationCompatibilityDimension
    left_version: SemanticVersion
    right_dimension: PtmLocalizationCompatibilityDimension
    right_version: SemanticVersion
    state: PtmLocalizationCompatibilityState

    @field_validator("rule_id")
    @classmethod
    def rule_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("rule", value)

    @model_validator(mode="after")
    def dimensions_are_distinct(self) -> PtmLocalizationCompatibilityRule:
        if self.left_dimension is self.right_dimension:
            raise ValueError("compatibility rules must relate distinct dimensions")
        return self


class PtmLocalizationAssaySpecimenPolicy(FrozenModel):
    policy_id: Identifier
    assay_kind: PtmLocalizationAssayKind
    specimen_kind: PtmLocalizationSpecimenKind
    assay_protocol_version: SemanticVersion
    specimen_processing_version: SemanticVersion
    support_domain: PtmLocalizationSupportDomain
    evidence: ArtifactReference

    @field_validator("policy_id")
    @classmethod
    def policy_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("policy", value)

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m05-01.policy+json"}),
        )


class PtmLocalizationUnresolvedRule(FrozenModel):
    state: PtmLocalizationUnresolvedState
    action: PtmLocalizationUnresolvedAction


class VariantPeptideHandoffRequirements(FrozenModel):
    parent_target: Literal["variant_peptide"] = M0501_PARENT_TARGET
    required_receipt_roles: tuple[VariantPeptideHandoffRole, ...] = Field(
        min_length=len(VariantPeptideHandoffRole),
        max_length=len(VariantPeptideHandoffRole),
    )
    emits_variant_peptide: Literal[False] = False
    evidence: ArtifactReference

    @field_validator("required_receipt_roles")
    @classmethod
    def roles_are_canonical(
        cls, values: tuple[VariantPeptideHandoffRole, ...]
    ) -> tuple[VariantPeptideHandoffRole, ...]:
        return tuple(_canonical(values))

    @field_validator("emits_variant_peptide", mode="before")
    @classmethod
    def emission_is_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m05-01.policy+json"}),
        )

    @model_validator(mode="after")
    def roles_are_exact(self) -> VariantPeptideHandoffRequirements:
        if set(self.required_receipt_roles) != set(VariantPeptideHandoffRole):
            raise ValueError("variant-peptide handoff requires every receipt role exactly once")
        return self


class PtmLocalizationProtocolSchema(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion
    unit_system_version: SemanticVersion
    required_identity_keys: tuple[PtmLocalizationIdentityKey, ...] = Field(
        min_length=1,
        max_length=M0501_IDENTITY_KEY_COUNT,
    )
    unresolved_rules: tuple[PtmLocalizationUnresolvedRule, ...] = Field(
        min_length=1,
        max_length=M0501_UNRESOLVED_STATE_COUNT,
    )
    reference_bundle: PtmLocalizationReferenceBundle
    controlled_vocabularies: tuple[PtmLocalizationControlledVocabulary, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_APPROVED_VERSIONS,
    )
    unit_policies: tuple[PtmLocalizationUnitPolicy, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_UNIT_POLICIES,
    )
    metadata_fields: tuple[PtmLocalizationMetadataFieldPolicy, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_METADATA_FIELDS,
    )
    compatibility_rules: tuple[PtmLocalizationCompatibilityRule, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_COMPATIBILITY_RULES,
    )
    assay_specimen_policy: PtmLocalizationAssaySpecimenPolicy
    variant_peptide_handoff: VariantPeptideHandoffRequirements
    evidence: ArtifactReference

    @field_validator("schema_id")
    @classmethod
    def schema_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("schema", value)

    @field_validator(
        "required_identity_keys",
        "unresolved_rules",
        "controlled_vocabularies",
        "unit_policies",
        "metadata_fields",
        "compatibility_rules",
    )
    @classmethod
    def semantic_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return _canonical(values)

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m05-01.policy+json"}),
        )

    @model_validator(mode="after")
    def declaration_identities_are_unique(self) -> PtmLocalizationProtocolSchema:
        collections: tuple[tuple[str, ...], ...] = (
            tuple(item.vocabulary_id for item in self.controlled_vocabularies),
            tuple(item.unit_policy_id for item in self.unit_policies),
            tuple(item.field_policy_id for item in self.metadata_fields),
            tuple(item.rule_id for item in self.compatibility_rules),
            tuple(item.state.value for item in self.unresolved_rules),
            tuple(item.field_name.value for item in self.metadata_fields),
            tuple(item.quantity.value for item in self.unit_policies),
        )
        if any(len(values) != len(set(values)) for values in collections):
            raise ValueError("protocol declaration identities and semantic roles must be unique")
        evidence = (
            self.assay_specimen_policy.evidence,
            self.variant_peptide_handoff.evidence,
            self.evidence,
        )
        if len({item.artifact_id for item in evidence}) != len(evidence) or len(
            {item.digest for item in evidence}
        ) != len(evidence):
            raise ValueError("protocol policy evidence identities and digests must be distinct")
        return self


class ApprovedPtmLocalizationReferenceBundle(FrozenModel):
    bundle_id: Identifier
    version: SemanticVersion
    bundle_digest: Sha256Digest

    @field_validator("bundle_id")
    @classmethod
    def bundle_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("bundle", value)


class ApprovedPtmLocalizationVocabulary(FrozenModel):
    vocabulary_id: Identifier
    version: SemanticVersion

    @field_validator("vocabulary_id")
    @classmethod
    def vocabulary_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("vocabulary", value)


class ReviewedPtmLocalizationConformanceProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    protocol_schema_id: Identifier
    protocol_schema_version: SemanticVersion
    protocol_schema_digest: Sha256Digest
    approved_reference_bundles: tuple[ApprovedPtmLocalizationReferenceBundle, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_APPROVED_REFERENCE_BUNDLES,
    )
    approved_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_APPROVED_VERSIONS,
    )
    approved_assay_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_APPROVED_VERSIONS,
    )
    approved_specimen_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_APPROVED_VERSIONS,
    )
    approved_vocabulary_versions: tuple[ApprovedPtmLocalizationVocabulary, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_APPROVED_VERSIONS,
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_APPROVED_VERSIONS,
    )
    approved_assay_specimen_policy_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1,
        max_length=M0501_MAX_APPROVED_VERSIONS,
    )
    allow_unreviewed_compatibility: Literal[False] = False
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("profile_id")
    @classmethod
    def profile_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("profile", value)

    @field_validator("protocol_schema_id")
    @classmethod
    def schema_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("schema", value)

    @field_validator("reviewed_by")
    @classmethod
    def reviewer_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("reviewer", value)

    @field_validator("allow_unreviewed_compatibility", mode="before")
    @classmethod
    def override_is_strict(cls, value: object) -> object:
        return _strict_bool(value)

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(
            value,
            media_types=frozenset({"application/vnd.glio-proteogen.m05-01.profile+json"}),
        )

    @field_validator(
        "approved_reference_bundles",
        "approved_protocol_versions",
        "approved_assay_versions",
        "approved_specimen_versions",
        "approved_vocabulary_versions",
        "approved_unit_system_versions",
        "approved_assay_specimen_policy_digests",
    )
    @classmethod
    def approved_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return _canonical(values)

    @model_validator(mode="after")
    def approved_identities_are_unique(self) -> ReviewedPtmLocalizationConformanceProfile:
        bundles = tuple((item.bundle_id, item.version) for item in self.approved_reference_bundles)
        vocabularies = tuple(
            (item.vocabulary_id, item.version) for item in self.approved_vocabulary_versions
        )
        if len(bundles) != len(set(bundles)) or len(vocabularies) != len(set(vocabularies)):
            raise ValueError("reviewed profile identities must be unique")
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
        references.consent.state.value != "granted"
        or references.identity_lineage.state.value != "resolved"
        or any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic)
    ):
        raise ValueError("PTM-localization protocol evaluation is not authorized")


def _validate_context_opacity(context: ExecutionContext) -> None:
    opaque_ptm_localization_protocol_identifier("request", context.request_id)
    opaque_ptm_localization_protocol_identifier("actor", context.actor_id)
    controls = (
        context.references.approved_configuration,
        context.references.identity_lineage,
        context.references.provenance,
        context.references.consent,
        context.references.quality,
        context.references.support,
        context.references.intended_use,
    )
    for control in controls:
        opaque_ptm_localization_protocol_identifier("decision", control.decision_id)
        _owned_artifact(
            control.evidence,
            media_types=frozenset({"application/vnd.glio-proteogen.control+json"}),
        )


class EvaluatePtmLocalizationProtocolRequest(FrozenModel):
    operation: Literal["evaluate_ptm_localization_protocol"] = M0501_OPERATION
    contract_version: Literal["1.0.0"] = M0501_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    protocol_schema: PtmLocalizationProtocolSchema
    conformance_profile: ReviewedPtmLocalizationConformanceProfile
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("request_id")
    @classmethod
    def request_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("request", value)

    @model_validator(mode="after")
    def request_is_authorized_and_pinned(self) -> EvaluatePtmLocalizationProtocolRequest:
        _require_authorized_context(self.context)
        _validate_context_opacity(self.context)
        if self.request_id != self.context.request_id:
            raise ValueError("request identifier must equal authorized context identifier")
        profile = self.conformance_profile
        protocol = self.protocol_schema
        if (
            profile.protocol_schema_id != protocol.schema_id
            or profile.protocol_schema_version != protocol.version
            or profile.protocol_schema_digest != protocol_digest(protocol)
        ):
            raise ValueError("reviewed profile does not pin the supplied protocol schema")
        if profile.reviewed_at > self.context.occurred_at:
            raise ValueError("reviewed profile cannot postdate protocol evaluation")
        if self.context.references.approved_configuration.evidence.digest != configuration_digest(
            protocol, profile
        ):
            raise ValueError("approved configuration does not bind protocol and profile")
        controls = (
            self.context.references.approved_configuration,
            self.context.references.identity_lineage,
            self.context.references.provenance,
            self.context.references.consent,
            self.context.references.quality,
            self.context.references.support,
            self.context.references.intended_use,
        )
        if len({item.evidence.artifact_id for item in controls}) != len(controls) or len(
            {item.evidence.digest for item in controls}
        ) != len(controls):
            raise ValueError(
                "authorization controls require distinct evidence identities and digests"
            )
        protocol_evidence_index(self)
        if len(canonical_json_bytes(self)) > M0501_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M05-01 request exceeds the governed byte cap")
        return self


def replay_ptm_localization_protocol_request(
    request: EvaluatePtmLocalizationProtocolRequest,
) -> EvaluatePtmLocalizationProtocolRequest:
    """Reconstruct a request strictly so copied or mutated nested models cannot bypass replay."""

    replayed = EvaluatePtmLocalizationProtocolRequest.model_validate(
        request.model_dump(mode="python", exclude_none=False),
        strict=True,
    )
    if replayed != request:
        raise ValueError("request is not equal to its strict replay")
    return replayed


def preflight_authorized(value: object) -> None:
    """Check all seven controls without traversing protocol or profile content."""

    if isinstance(value, EvaluatePtmLocalizationProtocolRequest):
        _require_authorized_context(value.context)
        return
    value_mro = type.__getattribute__(type(value), "__mro__")
    if dict not in value_mro:
        raise ValueError("authorization preflight requires an exact request object or dict")
    request_mapping = cast("dict[object, object]", value)
    if any(type(key) is not str for key in dict.keys(request_mapping)):
        raise ValueError("authorization preflight requires exact string keys")
    context = dict.get(request_mapping, "context")
    if type(context) is not dict:
        raise ValueError("authorization preflight requires an exact context dict")
    context_mapping = cast("dict[object, object]", context)
    references = dict.get(context_mapping, "references")
    if type(references) is not dict:
        raise ValueError("authorization preflight requires exact reference controls")
    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    reference_mapping = cast("dict[object, object]", references)
    states: dict[str, object] = {}
    for role, expected_state in expected.items():
        control = dict.get(reference_mapping, role)
        if type(control) is not dict:
            raise ValueError("authorization preflight requires every exact control object")
        control_mapping = cast("dict[object, object]", control)
        state = dict.get(control_mapping, "state")
        states[role] = state
        if state != expected_state:
            raise ValueError("PTM-localization protocol evaluation is not authorized")
    if len(states) != len(expected):
        raise ValueError("authorization preflight requires exactly seven controls")


def _profile_supports_protocol(
    protocol: PtmLocalizationProtocolSchema,
    profile: ReviewedPtmLocalizationConformanceProfile,
) -> bool:
    bundle = protocol.reference_bundle
    approved_bundle = ApprovedPtmLocalizationReferenceBundle(
        bundle_id=bundle.bundle_id,
        version=bundle.version,
        bundle_digest=reference_bundle_digest(bundle),
    )
    approved_vocabularies = {
        (item.vocabulary_id, item.version) for item in profile.approved_vocabulary_versions
    }
    return (
        protocol.assay_specimen_policy.support_domain
        is PtmLocalizationSupportDomain.REVIEWED_SUPPORTED
        and protocol.version in profile.approved_protocol_versions
        and approved_bundle in profile.approved_reference_bundles
        and protocol.assay_specimen_policy.assay_protocol_version in profile.approved_assay_versions
        and protocol.assay_specimen_policy.specimen_processing_version
        in profile.approved_specimen_versions
        and all(
            (item.vocabulary_id, item.version) in approved_vocabularies
            for item in protocol.controlled_vocabularies
        )
        and protocol.unit_system_version in profile.approved_unit_system_versions
        and assay_specimen_policy_digest(protocol.assay_specimen_policy)
        in profile.approved_assay_specimen_policy_digests
    )


def _units_are_complete(protocol: PtmLocalizationProtocolSchema) -> bool:
    return {item.quantity: item.unit for item in protocol.unit_policies} == _EXPECTED_UNIT


def _metadata_is_complete(protocol: PtmLocalizationProtocolSchema) -> bool:
    policies = {item.field_name: item for item in protocol.metadata_fields}
    fields_complete = set(policies) == set(PtmLocalizationMetadataFieldName) and all(
        item.required and item.minimum_cardinality == 1 and item.maximum_cardinality == 1
        for item in policies.values()
    )
    meanings = {
        term.meaning.value
        for vocabulary in protocol.controlled_vocabularies
        for term in vocabulary.terms
    }
    return fields_complete and {state.value for state in PtmLocalizationUnresolvedState}.issubset(
        meanings
    )


def _compatibility_is_complete(protocol: PtmLocalizationProtocolSchema) -> bool:
    expected_pairs = {
        frozenset(
            {
                PtmLocalizationCompatibilityDimension.ASSAY,
                PtmLocalizationCompatibilityDimension.SPECIMEN,
            }
        ),
        frozenset(
            {
                PtmLocalizationCompatibilityDimension.ASSAY,
                PtmLocalizationCompatibilityDimension.VOCABULARY,
            }
        ),
        frozenset(
            {
                PtmLocalizationCompatibilityDimension.ASSAY,
                PtmLocalizationCompatibilityDimension.UNIT_SYSTEM,
            }
        ),
        frozenset(
            {
                PtmLocalizationCompatibilityDimension.UNIT_SYSTEM,
                PtmLocalizationCompatibilityDimension.PARENT_TARGET,
            }
        ),
    }
    actual_pairs = {
        frozenset({item.left_dimension, item.right_dimension})
        for item in protocol.compatibility_rules
    }
    return expected_pairs.issubset(actual_pairs) and all(
        item.state is PtmLocalizationCompatibilityState.COMPATIBLE
        for item in protocol.compatibility_rules
    )


def _unresolved_semantics_are_complete(protocol: PtmLocalizationProtocolSchema) -> bool:
    return {item.state: item.action for item in protocol.unresolved_rules} == (
        _EXPECTED_UNRESOLVED_ACTION
    )


class PtmLocalizationProtocolConformanceFinding(FrozenModel):
    finding_id: Identifier
    section: PtmLocalizationProtocolSection
    state: PtmLocalizationProtocolFindingState
    reason_code: Identifier
    message: NonEmptyStr

    @field_validator("finding_id")
    @classmethod
    def finding_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("finding.m0501", value)


_SECTION_MESSAGE: Final = {
    PtmLocalizationProtocolSection.IDENTITY: "Mandatory identity-key declarations are closed.",
    PtmLocalizationProtocolSection.VERSIONS: "Protocol and reference versions are reviewed.",
    PtmLocalizationProtocolSection.UNITS: "Unit declarations are complete and quantity-compatible.",
    PtmLocalizationProtocolSection.COMPLETENESS: (
        "Mandatory metadata and vocabularies are complete."
    ),
    PtmLocalizationProtocolSection.ASSAY_SUPPORT: (
        "Assay and specimen policy is in the reviewed support domain."
    ),
    PtmLocalizationProtocolSection.PARENT_QUALITY: (
        "Variant-peptide parent handoff and quality controls are closed."
    ),
    PtmLocalizationProtocolSection.COMPATIBILITY: (
        "Required compatibility relationships are reviewed and compatible."
    ),
    PtmLocalizationProtocolSection.UNRESOLVED_SEMANTICS: (
        "Unresolved states retain distinct governed actions."
    ),
}


def _finding(
    section: PtmLocalizationProtocolSection,
    state: PtmLocalizationProtocolFindingState,
) -> PtmLocalizationProtocolConformanceFinding:
    reason = f"ptm_protocol.{section.value}.{state.value}"
    content = {
        "section": section.value,
        "state": state.value,
        "reason_code": reason,
        "message": _SECTION_MESSAGE[section],
    }
    suffix = sha256_digest(content).removeprefix("sha256:")
    return PtmLocalizationProtocolConformanceFinding(
        finding_id=f"finding.m0501.{suffix}",
        section=section,
        state=state,
        reason_code=reason,
        message=_SECTION_MESSAGE[section],
    )


def expected_protocol_findings(
    protocol: PtmLocalizationProtocolSchema,
    profile: ReviewedPtmLocalizationConformanceProfile,
) -> tuple[PtmLocalizationProtocolConformanceFinding, ...]:
    """Derive the exact eight-section conformance decision without scientific inference."""

    if not _profile_supports_protocol(protocol, profile):
        return tuple(
            _finding(section, PtmLocalizationProtocolFindingState.INDETERMINATE)
            for section in PtmLocalizationProtocolSection
        )
    checks = {
        PtmLocalizationProtocolSection.IDENTITY: set(protocol.required_identity_keys)
        == set(PtmLocalizationIdentityKey),
        PtmLocalizationProtocolSection.VERSIONS: True,
        PtmLocalizationProtocolSection.UNITS: _units_are_complete(protocol),
        PtmLocalizationProtocolSection.COMPLETENESS: _metadata_is_complete(protocol),
        PtmLocalizationProtocolSection.ASSAY_SUPPORT: True,
        PtmLocalizationProtocolSection.PARENT_QUALITY: (
            protocol.variant_peptide_handoff.parent_target == M0501_PARENT_TARGET
            and not protocol.variant_peptide_handoff.emits_variant_peptide
        ),
        PtmLocalizationProtocolSection.COMPATIBILITY: _compatibility_is_complete(protocol),
        PtmLocalizationProtocolSection.UNRESOLVED_SEMANTICS: (
            _unresolved_semantics_are_complete(protocol)
        ),
    }
    return tuple(
        _finding(
            section,
            PtmLocalizationProtocolFindingState.PASS
            if checks[section]
            else PtmLocalizationProtocolFindingState.FAIL,
        )
        for section in PtmLocalizationProtocolSection
    )


def _status_and_disposition(
    findings: tuple[PtmLocalizationProtocolConformanceFinding, ...],
) -> tuple[
    PtmLocalizationProtocolConformanceStatus,
    PtmLocalizationProtocolConformanceDisposition,
]:
    if any(item.state is PtmLocalizationProtocolFindingState.INDETERMINATE for item in findings):
        return (
            PtmLocalizationProtocolConformanceStatus.INDETERMINATE,
            PtmLocalizationProtocolConformanceDisposition.ABSTAINED,
        )
    if any(item.state is PtmLocalizationProtocolFindingState.FAIL for item in findings):
        return (
            PtmLocalizationProtocolConformanceStatus.NONCONFORMANT,
            PtmLocalizationProtocolConformanceDisposition.QUARANTINED,
        )
    return (
        PtmLocalizationProtocolConformanceStatus.CONFORMANT,
        PtmLocalizationProtocolConformanceDisposition.CONFORMANT,
    )


class PtmLocalizationProtocolSectionReceipt(FrozenModel):
    section: PtmLocalizationProtocolSection
    finding_id: Identifier
    state: PtmLocalizationProtocolFindingState

    @field_validator("finding_id")
    @classmethod
    def finding_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("finding.m0501", value)


class PtmLocalizationProtocolReceipt(FrozenModel):
    protocol_digest: Sha256Digest
    profile_digest: Sha256Digest
    configuration_digest: Sha256Digest
    reference_bundle_digest: Sha256Digest
    assay_specimen_policy_digest: Sha256Digest
    identity_subject_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    parent_target: Literal["variant_peptide"] = M0501_PARENT_TARGET
    sections: tuple[PtmLocalizationProtocolSectionReceipt, ...] = Field(
        min_length=M0501_SECTION_COUNT,
        max_length=M0501_SECTION_COUNT,
    )
    disposition: PtmLocalizationProtocolConformanceDisposition
    receipt_digest: Sha256Digest

    @field_validator("sections")
    @classmethod
    def sections_are_canonical(
        cls, values: tuple[PtmLocalizationProtocolSectionReceipt, ...]
    ) -> tuple[PtmLocalizationProtocolSectionReceipt, ...]:
        if {item.section for item in values} != set(PtmLocalizationProtocolSection):
            raise ValueError("receipt requires every conformance section exactly once")
        return tuple(sorted(values, key=lambda item: _SECTION_ORDER[item.section]))

    @model_validator(mode="after")
    def self_digest_is_exact(self) -> PtmLocalizationProtocolReceipt:
        if self.receipt_digest != receipt_digest(self):
            raise ValueError("receipt digest does not match canonical receipt content")
        return self


def expected_protocol_receipt(
    request: EvaluatePtmLocalizationProtocolRequest,
) -> PtmLocalizationProtocolReceipt:
    findings = expected_protocol_findings(request.protocol_schema, request.conformance_profile)
    _, disposition = _status_and_disposition(findings)
    payload: dict[str, object] = {
        "protocol_digest": protocol_digest(request.protocol_schema),
        "profile_digest": profile_digest(request.conformance_profile),
        "configuration_digest": configuration_digest(
            request.protocol_schema, request.conformance_profile
        ),
        "reference_bundle_digest": reference_bundle_digest(
            request.protocol_schema.reference_bundle
        ),
        "assay_specimen_policy_digest": assay_specimen_policy_digest(
            request.protocol_schema.assay_specimen_policy
        ),
        "identity_subject_digest": request.context.references.identity_lineage.binding_digest,
        "intended_use_evidence_digest": (request.context.references.intended_use.evidence.digest),
        "parent_target": M0501_PARENT_TARGET,
        "sections": tuple(
            PtmLocalizationProtocolSectionReceipt(
                section=item.section,
                finding_id=item.finding_id,
                state=item.state,
            )
            for item in findings
        ),
        "disposition": disposition,
        "receipt_digest": "sha256:" + ("0" * 64),
    }
    payload["receipt_digest"] = receipt_digest(payload)
    return PtmLocalizationProtocolReceipt.model_validate(payload, strict=True)


def protocol_evidence_index(
    request: EvaluatePtmLocalizationProtocolRequest,
) -> tuple[EvidenceReference, ...]:
    """Return the exact privacy-minimized 15-item evidence index."""

    references = request.context.references
    protocol = request.protocol_schema
    artifacts = (
        references.approved_configuration.evidence,
        references.identity_lineage.evidence,
        references.provenance.evidence,
        references.consent.evidence,
        references.quality.evidence,
        references.support.evidence,
        references.intended_use.evidence,
        *(item.reference for item in protocol.reference_bundle.references),
        protocol.reference_bundle.manifest_reference,
        protocol.assay_specimen_policy.evidence,
        protocol.variant_peptide_handoff.evidence,
        protocol.evidence,
        request.conformance_profile.evidence,
    )
    if (
        len(artifacts) != M0501_EVIDENCE_COUNT
        or len({item.artifact_id for item in artifacts}) != M0501_EVIDENCE_COUNT
        or len({item.digest for item in artifacts}) != M0501_EVIDENCE_COUNT
    ):
        raise ValueError("M05-01 requires exactly 15 distinct evidence artifacts and digests")
    return tuple(
        sorted(
            (
                EvidenceReference(
                    reference=item,
                    role="evidence",
                    claim="Caller-declared content-addressed M05-01 protocol evidence.",
                )
                for item in artifacts
            ),
            key=canonical_json_bytes,
        )
    )


def expected_support(
    disposition: PtmLocalizationProtocolConformanceDisposition,
) -> SupportDecision:
    if disposition is PtmLocalizationProtocolConformanceDisposition.CONFORMANT:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="ptm_localization_protocol_conformant",
            rationale="All reviewed M05-01 protocol conformance sections passed.",
        )
    if disposition is PtmLocalizationProtocolConformanceDisposition.ABSTAINED:
        return SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="ptm_localization_protocol_unsupported",
            rationale=(
                "The protocol is outside the reviewed M05-01 support domain; no negative "
                "finding is emitted."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="ptm_localization_protocol_quarantined",
        rationale=(
            "A supported protocol declaration failed conformance and requires external review."
        ),
    )


def expected_uncertainty() -> UncertaintyProfile:
    rationales = (
        "Measurement uncertainty is not estimated because M05-01 inspects metadata only.",
        "Sampling uncertainty is not estimated because M05-01 receives no observations.",
        "Parameter uncertainty is not estimated because M05-01 fits no parameters.",
        "Model-form uncertainty is not estimated because M05-01 executes no model.",
        "Identification uncertainty remains with the upstream evidence owner.",
        "Support uncertainty is represented by reviewed-domain conformance or abstention.",
        "Transport uncertainty is not estimated at this schema-only G0 boundary.",
    )
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in rationales
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=tuple(
            sorted(
                (
                    "No calibrated probability is emitted; the support domain is explicitly "
                    "narrowed.",
                    "Unsupported, unresolved, novel, or OOD assay/specimen declarations abstain.",
                    "Supported metadata incompatibility changes only conformance and quarantine "
                    "disposition.",
                )
            )
        ),
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code="ptm_protocol_conformance_only",
                    statement=(
                        "M05-01 validates caller-declared protocol metadata only and performs no "
                        "PTM localization or scientific inference."
                    ),
                ),
                Limitation(
                    code="external_authority_unverified",
                    statement=(
                        "Reference, configuration, identity, consent, support, quality, and review "
                        "authorities remain caller-declared."
                    ),
                ),
                Limitation(
                    code="variant_peptide_not_emitted",
                    statement=(
                        "The result preserves variant peptide only as the parent target and emits "
                        "no peptide, proteogenomic state, proteotype, subtype, kinase, fusion, or "
                        "treatment claim."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def _control_decisions(
    request: EvaluatePtmLocalizationProtocolRequest,
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
    request: EvaluatePtmLocalizationProtocolRequest,
    receipt: PtmLocalizationProtocolReceipt | None = None,
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
        assay_specimen_policy_digest(request.protocol_schema.assay_specimen_policy),
        active_receipt.receipt_digest,
        *(item.reference.digest for item in evidence),
    }
    if request.supersedes_result_digest is not None:
        input_digests.add(request.supersedes_result_digest)
    suffix = request_hash.removeprefix("sha256:")
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m0501.{suffix}",
        actor_id=request.context.actor_id,
        module_id=M0501_MODULE_ID,
        module_version=M0501_CONTRACT_VERSION,
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


class PtmLocalizationProtocolConformanceResult(FrozenModel):
    output_type: Literal["ptm_localization_protocol_conformance_result"] = (
        "ptm_localization_protocol_conformance_result"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0501_CONTRACT_VERSION
    request_digest: Sha256Digest
    protocol_digest: Sha256Digest
    profile_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluatePtmLocalizationProtocolRequest
    receipt: PtmLocalizationProtocolReceipt
    findings: tuple[PtmLocalizationProtocolConformanceFinding, ...] = Field(
        min_length=M0501_SECTION_COUNT,
        max_length=M0501_SECTION_COUNT,
    )
    status: PtmLocalizationProtocolConformanceStatus
    disposition: PtmLocalizationProtocolConformanceDisposition
    parent_target: Literal["variant_peptide"] = M0501_PARENT_TARGET
    emits_variant_peptide: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    localizes_ptm: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream_evidence: Literal[False] = False
    infers_identity_or_consent: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=M0501_EVIDENCE_COUNT,
        max_length=M0501_EVIDENCE_COUNT,
    )
    limitations: tuple[Limitation, ...] = Field(
        min_length=M0501_LIMITATION_COUNT,
        max_length=M0501_LIMITATION_COUNT,
    )
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("result_id")
    @classmethod
    def result_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_ptm_localization_protocol_identifier("result.m0501", value)

    @field_validator(
        "emits_variant_peptide",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "localizes_ptm",
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
    def findings_are_in_section_order(
        cls, values: tuple[PtmLocalizationProtocolConformanceFinding, ...]
    ) -> tuple[PtmLocalizationProtocolConformanceFinding, ...]:
        if {item.section for item in values} != set(PtmLocalizationProtocolSection):
            raise ValueError("result requires every conformance section exactly once")
        return tuple(sorted(values, key=lambda item: _SECTION_ORDER[item.section]))

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
    def result_is_exact_replay(self) -> PtmLocalizationProtocolConformanceResult:
        request = replay_ptm_localization_protocol_request(self.request)
        request_hash = canonical_request_digest(request)
        suffix = request_hash.removeprefix("sha256:")
        if (
            self.result_id != f"result.m0501.{suffix}"
            or self.request_digest != request_hash
            or self.protocol_digest != protocol_digest(request.protocol_schema)
            or self.profile_digest != profile_digest(request.conformance_profile)
            or self.configuration_digest
            != configuration_digest(request.protocol_schema, request.conformance_profile)
        ):
            raise ValueError("result identifiers and protocol bindings are inconsistent")
        expected_receipt = expected_protocol_receipt(request)
        expected_findings = expected_protocol_findings(
            request.protocol_schema, request.conformance_profile
        )
        expected_status, expected_disposition = _status_and_disposition(expected_findings)
        if self.receipt != expected_receipt or self.findings != expected_findings:
            raise ValueError("result receipt or findings contradict the embedded request")
        expected_review = expected_disposition is not (
            PtmLocalizationProtocolConformanceDisposition.CONFORMANT
        )
        if (
            self.status is not expected_status
            or self.disposition is not expected_disposition
            or self.support != expected_support(expected_disposition)
            or self.human_review_required is not expected_review
        ):
            raise ValueError("result disposition, support, or review state contradicts findings")
        if self.uncertainty != expected_uncertainty():
            raise ValueError("result uncertainty exceeds the M05-01 declaration boundary")
        if self.provenance != expected_provenance(request, expected_receipt):
            raise ValueError("result provenance contradicts the embedded request")
        if self.evidence != protocol_evidence_index(request):
            raise ValueError("result evidence index contradicts the embedded request")
        if self.limitations != expected_limitations():
            raise ValueError("result limitations exceed the M05-01 authority boundary")
        if self.completed_at != request.context.occurred_at:
            raise ValueError("result completion time must equal authorized execution time")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_protocol_result(
    request: EvaluatePtmLocalizationProtocolRequest,
) -> PtmLocalizationProtocolConformanceResult:
    """Assemble and strictly replay the one exact result for a valid request."""

    replayed = replay_ptm_localization_protocol_request(request)
    request_hash = canonical_request_digest(replayed)
    findings = expected_protocol_findings(replayed.protocol_schema, replayed.conformance_profile)
    status, disposition = _status_and_disposition(findings)
    receipt = expected_protocol_receipt(replayed)
    payload: dict[str, object] = {
        "output_type": "ptm_localization_protocol_conformance_result",
        "result_id": f"result.m0501.{request_hash.removeprefix('sha256:')}",
        "result_version": M0501_CONTRACT_VERSION,
        "request_digest": request_hash,
        "protocol_digest": protocol_digest(replayed.protocol_schema),
        "profile_digest": profile_digest(replayed.conformance_profile),
        "configuration_digest": configuration_digest(
            replayed.protocol_schema, replayed.conformance_profile
        ),
        "result_digest": "sha256:" + ("0" * 64),
        "request": replayed,
        "receipt": receipt,
        "findings": findings,
        "status": status,
        "disposition": disposition,
        "parent_target": M0501_PARENT_TARGET,
        "emits_variant_peptide": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "localizes_ptm": False,
        "infers_kinase_activity": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream_evidence": False,
        "infers_identity_or_consent": False,
        "support": expected_support(disposition),
        "uncertainty": expected_uncertainty(),
        "provenance": expected_provenance(replayed, receipt),
        "evidence": protocol_evidence_index(replayed),
        "limitations": expected_limitations(),
        "human_review_required": disposition
        is not PtmLocalizationProtocolConformanceDisposition.CONFORMANT,
        "completed_at": replayed.context.occurred_at,
    }
    payload["result_digest"] = result_payload_digest(payload)
    return PtmLocalizationProtocolConformanceResult.model_validate(payload, strict=True)


__all__ = [
    "M0501_CONTRACT_VERSION",
    "M0501_EVIDENCE_COUNT",
    "M0501_GATE",
    "M0501_IDENTITY_KEY_COUNT",
    "M0501_INPUT_ROLE_COUNT",
    "M0501_LIMITATION_COUNT",
    "M0501_MAX_APPROVED_REFERENCE_BUNDLES",
    "M0501_MAX_APPROVED_VERSIONS",
    "M0501_MAX_CANONICAL_REQUEST_BYTES",
    "M0501_MAX_COMPATIBILITY_RULES",
    "M0501_MAX_METADATA_FIELDS",
    "M0501_MAX_UNIT_POLICIES",
    "M0501_MAX_VOCABULARY_TERMS",
    "M0501_MODULE_ID",
    "M0501_OPERATION",
    "M0501_OWNER",
    "M0501_PARENT_TARGET",
    "M0501_SAFETY_CLASS",
    "M0501_SECTION_COUNT",
    "M0501_UNRESOLVED_STATE_COUNT",
    "ApprovedPtmLocalizationReferenceBundle",
    "ApprovedPtmLocalizationVocabulary",
    "EvaluatePtmLocalizationProtocolRequest",
    "PtmLocalizationAssayKind",
    "PtmLocalizationAssaySpecimenPolicy",
    "PtmLocalizationCompatibilityDimension",
    "PtmLocalizationCompatibilityRule",
    "PtmLocalizationCompatibilityState",
    "PtmLocalizationControlledVocabulary",
    "PtmLocalizationIdentityKey",
    "PtmLocalizationInputReference",
    "PtmLocalizationInputRole",
    "PtmLocalizationMetadataFieldName",
    "PtmLocalizationMetadataFieldPolicy",
    "PtmLocalizationProtocolConformanceDisposition",
    "PtmLocalizationProtocolConformanceFinding",
    "PtmLocalizationProtocolConformanceResult",
    "PtmLocalizationProtocolConformanceStatus",
    "PtmLocalizationProtocolFindingState",
    "PtmLocalizationProtocolOpaqueNamespace",
    "PtmLocalizationProtocolReceipt",
    "PtmLocalizationProtocolSchema",
    "PtmLocalizationProtocolSection",
    "PtmLocalizationProtocolSectionReceipt",
    "PtmLocalizationQuantity",
    "PtmLocalizationReferenceBundle",
    "PtmLocalizationReferenceCardinality",
    "PtmLocalizationSpecimenKind",
    "PtmLocalizationSupportDomain",
    "PtmLocalizationUnit",
    "PtmLocalizationUnitPolicy",
    "PtmLocalizationUnresolvedAction",
    "PtmLocalizationUnresolvedRule",
    "PtmLocalizationUnresolvedState",
    "PtmLocalizationVocabularyMeaning",
    "PtmLocalizationVocabularyTerm",
    "ReviewedPtmLocalizationConformanceProfile",
    "VariantPeptideHandoffRequirements",
    "VariantPeptideHandoffRole",
    "expected_limitations",
    "expected_protocol_findings",
    "expected_protocol_receipt",
    "expected_protocol_result",
    "expected_provenance",
    "expected_support",
    "expected_uncertainty",
    "opaque_ptm_localization_protocol_identifier",
    "preflight_authorized",
    "protocol_evidence_index",
    "replay_ptm_localization_protocol_request",
]
