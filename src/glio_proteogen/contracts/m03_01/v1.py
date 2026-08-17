"""Strict M03-01 protein-inference protocol contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m03_01.canonical import (
    canonical_request_digest,
    configuration_digest,
    profile_digest,
    protocol_digest,
    protocol_section_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonInferenceResultModel,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0301_MODULE_ID: Final = "GLIO-PROTEOGEN-M03-01"
M0301_CONTRACT_VERSION: Final = "1.0.0"
M0301_MAX_THRESHOLDS: Final = 3
M0301_HANDOFF_ROLE_COUNT: Final = 7
M0301_CONFORMANT_SUPPORT_RATIONALE: Final = (
    "The declared protocol conforms to its exact reviewed profile."
)
M0301_QUARANTINED_SUPPORT_RATIONALE: Final = (
    "One or more reviewed protocol constraints failed and require review."
)
M0301_UNCERTAINTY_RATIONALES: Final = (
    "M03-01 does not inspect measurements or spectra.",
    "M03-01 does not estimate sampling uncertainty.",
    "The deterministic conformance evaluator fits no parameters.",
    "M03-01 executes no learned protein-inference model.",
    "No peptide or protein identification is performed.",
    "Support is a deterministic reviewed-profile decision.",
    "External receipt authorities are caller-declared.",
)
M0301_SENSITIVITY_NOTES: Final = (
    "A profile mismatch quarantines the protocol rather than changing its declarations.",
    "Unresolved accessions and ambiguity are never converted to negative findings.",
)
_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)


class ProteinInferenceApplicability(StrEnum):
    SHOTGUN_DDA = "shotgun_dda"
    DIA = "dia"
    TARGETED = "targeted"


class TargetDecoyStrategy(StrEnum):
    CONCATENATED = "concatenated"
    SEPARATE = "separate"
    PICKED = "picked"


class ErrorControlLevel(StrEnum):
    PSM = "psm"
    PEPTIDE = "peptide"
    PROTEIN_GROUP = "protein_group"


class ProteinErrorMeasure(StrEnum):
    Q_VALUE = "q_value"
    POSTERIOR_ERROR_PROBABILITY = "posterior_error_probability"
    PICKED_FDR = "picked_fdr"


class SharedPeptideStrategy(StrEnum):
    EXCLUDE = "exclude"
    GROUP_ONLY = "group_only"
    RAZOR = "razor"


class RazorTieBreak(StrEnum):
    NONE = "none"
    LEXICOGRAPHIC_ACCESSION = "lexicographic_accession"
    HIGHEST_UNIQUE_PEPTIDE_COUNT = "highest_unique_peptide_count"


class RepresentativeSelection(StrEnum):
    ACCESSION_PRIORITY = "accession_priority"
    MOST_UNIQUE_PEPTIDES = "most_unique_peptides"
    NONE = "none"


class HandoffReceiptRole(StrEnum):
    SEARCH_SPACE = "search_space"
    ERROR_CONTROL = "error_control"
    PEPTIDE_ELIGIBILITY = "peptide_eligibility"
    ASSIGNMENT = "assignment"
    PROTEIN_GROUP = "protein_group"
    AMBIGUITY = "ambiguity"
    PROVENANCE = "provenance"


class ProtocolSection(StrEnum):
    APPLICABILITY = "applicability"
    SEARCH_SPACE = "search_space"
    ERROR_CONTROL = "error_control"
    PEPTIDE_ELIGIBILITY = "peptide_eligibility"
    ASSIGNMENT = "assignment"
    GROUPING = "grouping"
    AMBIGUITY = "ambiguity"
    COMPLEX_HANDOFF = "complex_handoff"


class ProtocolConformanceStatus(StrEnum):
    CONFORMANT = "conformant"
    NONCONFORMANT = "nonconformant"
    INDETERMINATE = "indeterminate"


class ProtocolConformanceDisposition(StrEnum):
    CONFORMANT = "conformant"
    QUARANTINED = "quarantined"


class ProtocolFindingState(StrEnum):
    PASS = "pass"  # noqa: S105 - protocol conformance state, not a credential.
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class ProteinInferenceIdentityKey(StrEnum):
    PATIENT = "patient_id"
    SPECIMEN = "specimen_id"
    ALIQUOT = "aliquot_id"
    ANALYTE = "analyte_id"
    RUN = "run_id"


class DeclaredUnresolvedState(StrEnum):
    MISSING = "missing"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"
    REDACTED = "redacted"


class SearchSpaceComposition(FrozenModel):
    canonical_sequences: int = Field(gt=0, le=100_000_000)
    isoform_sequences: int = Field(ge=0, le=100_000_000)
    variant_sequences: int = Field(ge=0, le=100_000_000)
    contaminant_sequences: int = Field(ge=0, le=10_000_000)
    decoy_sequences: int = Field(gt=0, le=100_000_000)
    target_sequences: int = Field(gt=0, le=210_000_000)
    total_sequences: int = Field(gt=0, le=310_000_000)

    @model_validator(mode="after")
    def counts_close(self) -> SearchSpaceComposition:
        target = (
            self.canonical_sequences
            + self.isoform_sequences
            + self.variant_sequences
            + self.contaminant_sequences
        )
        if self.target_sequences != target or self.total_sequences != target + self.decoy_sequences:
            raise ValueError("search-space composition counts do not close")
        return self


class AccessionAliasPolicy(FrozenModel):
    versioned_accessions_required: Literal[True] = True
    aliases_must_resolve_uniquely: Literal[True] = True
    collisions_remain_unresolved: Literal[True] = True
    unversioned_guesses_forbidden: Literal[True] = True


class SearchSpaceReceipt(FrozenModel):
    namespace: Identifier
    release: SemanticVersion
    build_id: Identifier
    content_digest: Sha256Digest
    composition: SearchSpaceComposition
    target_decoy_strategy: TargetDecoyStrategy
    accession_alias_policy: AccessionAliasPolicy
    canonical_sequence_reference: ArtifactReference
    decoy_reference: ArtifactReference
    isoform_reference: ArtifactReference | None = None
    variant_reference: ArtifactReference | None = None
    contaminant_reference: ArtifactReference | None = None
    evidence: ArtifactReference

    @model_validator(mode="after")
    def variant_reference_closes_composition(self) -> SearchSpaceReceipt:
        pairs = (
            (self.composition.isoform_sequences, self.isoform_reference, "isoform"),
            (self.composition.variant_sequences, self.variant_reference, "variant"),
            (self.composition.contaminant_sequences, self.contaminant_reference, "contaminant"),
        )
        if any((count > 0) != (reference is not None) for count, reference, _ in pairs):
            raise ValueError("optional search-space components require exact pinned references")
        digests = tuple(
            item.digest
            for item in (
                self.canonical_sequence_reference,
                self.decoy_reference,
                self.isoform_reference,
                self.variant_reference,
                self.contaminant_reference,
                self.evidence,
            )
            if item is not None
        )
        if len(digests) != len(set(digests)):
            raise ValueError("search-space references require distinct content digests")
        return self


class ErrorControlThreshold(FrozenModel):
    level: ErrorControlLevel
    measure: ProteinErrorMeasure
    maximum: float = Field(ge=0.0, le=1.0)
    scale: Literal["fraction"] = "fraction"


class ProteinErrorControlPolicy(FrozenModel):
    target_decoy_strategy: TargetDecoyStrategy
    thresholds: tuple[ErrorControlThreshold, ...] = Field(
        min_length=1, max_length=M0301_MAX_THRESHOLDS
    )
    protein_level: ErrorControlLevel = ErrorControlLevel.PROTEIN_GROUP

    @model_validator(mode="after")
    def thresholds_are_unique_and_group_level(self) -> ProteinErrorControlPolicy:
        levels = tuple(item.level for item in self.thresholds)
        if len(levels) != len(set(levels)) or ErrorControlLevel.PROTEIN_GROUP not in levels:
            raise ValueError("error control needs unique levels including protein_group")
        if self.protein_level is not ErrorControlLevel.PROTEIN_GROUP:
            raise ValueError("protein inference error control must be protein-group level")
        for item in self.thresholds:
            if item.measure is ProteinErrorMeasure.PICKED_FDR and (
                item.level is not ErrorControlLevel.PROTEIN_GROUP
                or self.target_decoy_strategy is not TargetDecoyStrategy.PICKED
            ):
                raise ValueError("picked FDR is valid only for picked protein-group competition")
        return self


class PeptideEvidenceEligibilityPolicy(FrozenModel):
    min_length: int = Field(ge=5, le=100)
    max_length: int = Field(ge=5, le=200)
    max_missed_cleavages: int = Field(ge=0, le=10)
    max_variable_modifications: int = Field(ge=0, le=20)
    uniqueness_relative_to_search_space: Literal[True] = True
    include_decoy_and_contaminant_competitors: Literal[True] = True
    modification_vocabulary_reference: ArtifactReference

    @model_validator(mode="after")
    def length_interval_is_ordered(self) -> PeptideEvidenceEligibilityPolicy:
        if self.min_length > self.max_length:
            raise ValueError("peptide length interval is reversed")
        return self


class PeptideToProteinAssignmentPolicy(FrozenModel):
    shared_peptide_strategy: SharedPeptideStrategy
    razor_tie_break: RazorTieBreak
    shared_peptides_support_group_claims_only: Literal[True] = True
    razor_never_supports_member_specific_claim: Literal[True] = True

    @model_validator(mode="after")
    def razor_has_deterministic_tie_break(self) -> PeptideToProteinAssignmentPolicy:
        if (self.shared_peptide_strategy is SharedPeptideStrategy.RAZOR) == (
            self.razor_tie_break is RazorTieBreak.NONE
        ):
            raise ValueError("razor assignment requires exactly one deterministic tie break")
        return self


class ProteinGroupPolicy(FrozenModel):
    preserve_indistinguishable_members: Literal[True] = True
    representative_selection: RepresentativeSelection
    representative_is_display_only: Literal[True] = True
    representative_never_promotes_group_claim: Literal[True] = True


class AmbiguityReportingPolicy(FrozenModel):
    unresolved_is_not_negative: Literal[True] = True
    preserve_isoform_ambiguity: Literal[True] = True
    isoform_claim_requires_eligible_discriminating_peptide: Literal[True] = True
    variant_claim_requires_eligible_discriminating_peptide: Literal[True] = True
    variant_claim_requires_pinned_reference: Literal[True] = True


class ComplexActivityHandoffRequirements(FrozenModel):
    required_receipt_roles: tuple[HandoffReceiptRole, ...] = Field(
        min_length=M0301_HANDOFF_ROLE_COUNT,
        max_length=M0301_HANDOFF_ROLE_COUNT,
    )
    preserve_unresolved_groups: Literal[True] = True
    emit_activity_inference: Literal[False] = False
    activity_owner: Literal["downstream_complex_activity_module"] = (
        "downstream_complex_activity_module"
    )
    evidence: ArtifactReference

    @model_validator(mode="after")
    def roles_are_exact(self) -> ComplexActivityHandoffRequirements:
        if set(self.required_receipt_roles) != set(HandoffReceiptRole):
            raise ValueError("complex-activity handoff requires every receipt role exactly once")
        return self


class ProteinInferenceProtocolSchema(FrozenModel):
    schema_id: Identifier
    version: SemanticVersion
    applicability: ProteinInferenceApplicability
    assay_protocol_version: SemanticVersion
    specimen_processing_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    required_identity_keys: tuple[ProteinInferenceIdentityKey, ...] = Field(
        min_length=5, max_length=5
    )
    declared_unresolved_states: tuple[DeclaredUnresolvedState, ...] = Field(
        min_length=6, max_length=6
    )
    search_space: SearchSpaceReceipt
    error_control: ProteinErrorControlPolicy
    peptide_eligibility: PeptideEvidenceEligibilityPolicy
    assignment: PeptideToProteinAssignmentPolicy
    protein_grouping: ProteinGroupPolicy
    ambiguity: AmbiguityReportingPolicy
    complex_activity_handoff: ComplexActivityHandoffRequirements
    evidence: ArtifactReference

    @model_validator(mode="after")
    def strategies_match(self) -> ProteinInferenceProtocolSchema:
        if self.search_space.target_decoy_strategy is not self.error_control.target_decoy_strategy:
            raise ValueError("search-space and error-control target-decoy strategies must match")
        if set(self.required_identity_keys) != set(ProteinInferenceIdentityKey):
            raise ValueError("protocol must declare every mandatory protein-inference identity key")
        if set(self.declared_unresolved_states) != set(DeclaredUnresolvedState):
            raise ValueError("protocol must distinguish every governed unresolved state")
        evidence = (
            self.evidence,
            self.peptide_eligibility.modification_vocabulary_reference,
            self.complex_activity_handoff.evidence,
        )
        if len({item.digest for item in evidence}) != len(evidence):
            raise ValueError("protocol evidence roles require distinct content digests")
        return self


class ApprovedSearchSpace(FrozenModel):
    namespace: Identifier
    release: SemanticVersion
    build_id: Identifier
    content_digest: Sha256Digest


class ApprovedControlledVocabulary(FrozenModel):
    vocabulary_id: Identifier
    version: SemanticVersion


class ReviewedProteinInferenceConformanceProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    protocol_schema_id: Identifier
    protocol_schema_version: SemanticVersion
    protocol_schema_digest: Sha256Digest
    approved_applicabilities: tuple[ProteinInferenceApplicability, ...] = Field(
        min_length=1, max_length=3
    )
    approved_search_spaces: tuple[ApprovedSearchSpace, ...] = Field(min_length=1, max_length=256)
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=32
    )
    approved_specimen_processing_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=32
    )
    approved_controlled_vocabularies: tuple[ApprovedControlledVocabulary, ...] = Field(
        min_length=1, max_length=32
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(min_length=1, max_length=32)
    allowed_target_decoy_strategies: tuple[TargetDecoyStrategy, ...] = Field(
        min_length=1, max_length=3
    )
    allowed_protein_error_measures: tuple[ProteinErrorMeasure, ...] = Field(
        min_length=1, max_length=3
    )
    allowed_shared_peptide_strategies: tuple[SharedPeptideStrategy, ...] = Field(
        min_length=1, max_length=3
    )
    allowed_representative_selections: tuple[RepresentativeSelection, ...] = Field(
        min_length=1, max_length=3
    )
    max_psm_error_fraction: float = Field(ge=0.0, le=1.0)
    max_peptide_error_fraction: float = Field(ge=0.0, le=1.0)
    max_protein_group_error_fraction: float = Field(ge=0.0, le=1.0)
    min_peptide_length: int = Field(ge=5, le=100)
    max_peptide_length: int = Field(ge=5, le=200)
    max_missed_cleavages: int = Field(ge=0, le=10)
    max_variable_modifications: int = Field(ge=0, le=20)
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @model_validator(mode="after")
    def reviewed_sets_are_bounded_and_unique(self) -> ReviewedProteinInferenceConformanceProfile:
        collections = (
            self.approved_applicabilities,
            self.approved_search_spaces,
            self.approved_assay_protocol_versions,
            self.approved_specimen_processing_versions,
            self.approved_controlled_vocabularies,
            self.approved_unit_system_versions,
            self.allowed_target_decoy_strategies,
            self.allowed_protein_error_measures,
            self.allowed_shared_peptide_strategies,
            self.allowed_representative_selections,
        )
        if any(len(items) != len(set(items)) for items in collections):
            raise ValueError("reviewed profile collections must be unique")
        identities = tuple(
            (item.namespace, item.release, item.build_id) for item in self.approved_search_spaces
        )
        if len(identities) != len(set(identities)):
            raise ValueError("approved search-space identities must be unique")
        if self.min_peptide_length > self.max_peptide_length:
            raise ValueError("reviewed peptide length interval is reversed")
        return self


class EvaluateProteinInferenceProtocolRequest(FrozenModel):
    operation: Literal["evaluate_protein_inference_protocol"] = (
        "evaluate_protein_inference_protocol"
    )
    contract_version: Literal["1.0.0"] = M0301_CONTRACT_VERSION
    context: ExecutionContext
    protocol_schema: ProteinInferenceProtocolSchema
    conformance_profile: ReviewedProteinInferenceConformanceProfile
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_and_pinned(self) -> EvaluateProteinInferenceProtocolRequest:
        _require_authorized_context(self.context)
        protocol = self.protocol_schema
        profile = self.conformance_profile
        if (
            profile.protocol_schema_id != protocol.schema_id
            or profile.protocol_schema_version != protocol.version
            or profile.protocol_schema_digest != protocol_digest(protocol)
        ):
            raise ValueError("reviewed profile does not pin the supplied protocol schema")
        if profile.reviewed_at > self.context.occurred_at:
            raise ValueError("reviewed profile cannot postdate protocol evaluation")
        expected = configuration_digest(protocol, profile)
        if self.context.references.approved_configuration.evidence.digest != expected:
            raise ValueError("approved configuration does not bind protocol and profile")
        control_digests = tuple(
            item.evidence.digest
            for item in (
                self.context.references.approved_configuration,
                self.context.references.identity_lineage,
                self.context.references.provenance,
                self.context.references.consent,
                self.context.references.quality,
                self.context.references.support,
                self.context.references.intended_use,
            )
        )
        if len(control_digests) != len(set(control_digests)):
            raise ValueError("authorization controls require distinct evidence digests")
        return self


class ProtocolConformanceFinding(FrozenModel):
    section: ProtocolSection
    state: ProtocolFindingState
    reason_code: Identifier
    remediation_code: Identifier | None = None


def _finding(
    section: ProtocolSection,
    *,
    passed: bool,
    success_code: str,
    fail_code: str,
    remediation_code: str,
) -> ProtocolConformanceFinding:
    return ProtocolConformanceFinding(
        section=section,
        state=ProtocolFindingState.PASS if passed else ProtocolFindingState.FAIL,
        reason_code=success_code if passed else fail_code,
        remediation_code=None if passed else remediation_code,
    )


def expected_protocol_findings(
    protocol: ProteinInferenceProtocolSchema,
    profile: ReviewedProteinInferenceConformanceProfile,
) -> tuple[ProtocolConformanceFinding, ...]:
    """Derive the exact eight reviewed-domain findings from embedded declarations."""

    search_key = (
        protocol.search_space.namespace,
        protocol.search_space.release,
        protocol.search_space.build_id,
        protocol.search_space.content_digest,
    )
    approved_spaces = {
        (item.namespace, item.release, item.build_id, item.content_digest)
        for item in profile.approved_search_spaces
    }
    measures = {item.measure for item in protocol.error_control.thresholds}
    thresholds = {item.level: item for item in protocol.error_control.thresholds}
    peptide_threshold = thresholds.get(ErrorControlLevel.PEPTIDE)
    level_caps = {
        ErrorControlLevel.PSM: profile.max_psm_error_fraction,
        ErrorControlLevel.PEPTIDE: profile.max_peptide_error_fraction,
        ErrorControlLevel.PROTEIN_GROUP: profile.max_protein_group_error_fraction,
    }
    error_fractions_ok = all(
        threshold.maximum <= level_caps[threshold.level]
        for threshold in protocol.error_control.thresholds
    )
    peptide_fraction_ok = (
        peptide_threshold is None or peptide_threshold.maximum <= profile.max_peptide_error_fraction
    )
    eligibility = protocol.peptide_eligibility
    eligibility_ok = (
        eligibility.min_length >= profile.min_peptide_length
        and eligibility.max_length <= profile.max_peptide_length
        and eligibility.max_missed_cleavages <= profile.max_missed_cleavages
        and eligibility.max_variable_modifications <= profile.max_variable_modifications
    )
    applicability_ok = (
        protocol.applicability in profile.approved_applicabilities
        and protocol.assay_protocol_version in profile.approved_assay_protocol_versions
        and protocol.specimen_processing_version in profile.approved_specimen_processing_versions
        and ApprovedControlledVocabulary(
            vocabulary_id=protocol.controlled_vocabulary_id,
            version=protocol.controlled_vocabulary_version,
        )
        in profile.approved_controlled_vocabularies
        and protocol.unit_system_version in profile.approved_unit_system_versions
    )
    return (
        _finding(
            ProtocolSection.APPLICABILITY,
            passed=applicability_ok,
            success_code="applicability_and_versions_reviewed",
            fail_code="applicability_or_version_outside_reviewed_profile",
            remediation_code="select_reviewed_assay_specimen_vocabulary_and_unit_versions",
        ),
        _finding(
            ProtocolSection.SEARCH_SPACE,
            passed=search_key in approved_spaces,
            success_code="search_space_exact_build_approved",
            fail_code="search_space_build_not_approved",
            remediation_code="pin_reviewed_search_space_build",
        ),
        _finding(
            ProtocolSection.ERROR_CONTROL,
            passed=protocol.error_control.target_decoy_strategy
            in profile.allowed_target_decoy_strategies
            and measures.issubset(profile.allowed_protein_error_measures)
            and error_fractions_ok,
            success_code="error_control_reviewed_and_compatible",
            fail_code="error_control_outside_reviewed_profile",
            remediation_code="use_reviewed_error_control_strategy_measure_and_fraction_bounds",
        ),
        _finding(
            ProtocolSection.PEPTIDE_ELIGIBILITY,
            passed=eligibility_ok and peptide_fraction_ok,
            success_code="peptide_eligibility_reviewed",
            fail_code="peptide_eligibility_outside_reviewed_profile",
            remediation_code="use_reviewed_peptide_eligibility_and_error_bounds",
        ),
        _finding(
            ProtocolSection.ASSIGNMENT,
            passed=protocol.assignment.shared_peptide_strategy
            in profile.allowed_shared_peptide_strategies,
            success_code="shared_peptide_assignment_reviewed",
            fail_code="shared_peptide_assignment_not_reviewed",
            remediation_code="select_reviewed_shared_peptide_strategy",
        ),
        _finding(
            ProtocolSection.GROUPING,
            passed=protocol.protein_grouping.representative_selection
            in profile.allowed_representative_selections,
            success_code="protein_group_representation_reviewed",
            fail_code="representative_selection_not_reviewed",
            remediation_code="select_reviewed_representative_policy",
        ),
        _finding(
            ProtocolSection.AMBIGUITY,
            passed=True,
            success_code="ambiguity_and_discrimination_policy_closed",
            fail_code="ambiguity_policy_unsafe",
            remediation_code="preserve_unresolved_isoform_variant_ambiguity",
        ),
        _finding(
            ProtocolSection.COMPLEX_HANDOFF,
            passed=True,
            success_code="complex_activity_handoff_receipts_closed",
            fail_code="complex_activity_handoff_unsafe",
            remediation_code="restore_protocol_receipt_only_handoff",
        ),
    )


def protocol_evidence_index(
    request: EvaluateProteinInferenceProtocolRequest,
) -> tuple[EvidenceReference, ...]:
    """Return the exact privacy-minimized evidence index for a result."""

    references = request.context.references
    protocol = request.protocol_schema
    artifacts: tuple[ArtifactReference, ...] = (
        references.approved_configuration.evidence,
        references.identity_lineage.evidence,
        references.provenance.evidence,
        references.consent.evidence,
        references.quality.evidence,
        references.support.evidence,
        references.intended_use.evidence,
        protocol.search_space.canonical_sequence_reference,
        protocol.search_space.decoy_reference,
        protocol.search_space.evidence,
        protocol.peptide_eligibility.modification_vocabulary_reference,
        protocol.complex_activity_handoff.evidence,
        protocol.evidence,
        request.conformance_profile.evidence,
        *(
            (protocol.search_space.isoform_reference,)
            if protocol.search_space.isoform_reference is not None
            else ()
        ),
        *(
            (protocol.search_space.variant_reference,)
            if protocol.search_space.variant_reference is not None
            else ()
        ),
        *(
            (protocol.search_space.contaminant_reference,)
            if protocol.search_space.contaminant_reference is not None
            else ()
        ),
    )
    by_digest = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(
            reference=by_digest[digest],
            role="evidence",
            claim="Caller-declared content-addressed M03-01 protocol evidence.",
        )
        for digest in sorted(by_digest)
    )


class ProteinInferenceProtocolReceipt(FrozenModel):
    protocol_digest: Sha256Digest
    profile_digest: Sha256Digest
    configuration_digest: Sha256Digest
    search_space_digest: Sha256Digest
    error_control_digest: Sha256Digest
    assignment_digest: Sha256Digest
    protein_group_digest: Sha256Digest
    ambiguity_digest: Sha256Digest
    handoff_digest: Sha256Digest
    identity_subject_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    parent_target: Literal["complex_activity"] = "complex_activity"
    disposition: ProtocolConformanceDisposition


class ProteinInferenceProtocolConformanceResult(NonInferenceResultModel):
    output_type: Literal["protein_inference_protocol_conformance_result"] = (
        "protein_inference_protocol_conformance_result"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0301_CONTRACT_VERSION
    request_digest: Sha256Digest
    protocol_digest: Sha256Digest
    profile_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    context: ExecutionContext
    protocol_schema: ProteinInferenceProtocolSchema
    conformance_profile: ReviewedProteinInferenceConformanceProfile
    receipt: ProteinInferenceProtocolReceipt
    findings: tuple[ProtocolConformanceFinding, ...] = Field(min_length=8, max_length=8)
    status: ProtocolConformanceStatus
    disposition: ProtocolConformanceDisposition
    parent_target: Literal["complex_activity"] = "complex_activity"
    # M03-01 is a protocol/conformance boundary.  It never emits biological
    # identity, protein, proteoform, isoform, or glioma-specific claims.
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=32)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> ProteinInferenceProtocolConformanceResult:
        protocol_hash = protocol_digest(self.protocol_schema)
        active_profile_hash = profile_digest(self.conformance_profile)
        config_hash = configuration_digest(self.protocol_schema, self.conformance_profile)
        reconstructed_request = EvaluateProteinInferenceProtocolRequest(
            context=self.context,
            protocol_schema=self.protocol_schema,
            conformance_profile=self.conformance_profile,
            supersedes_result_digest=self.supersedes_result_digest,
        )
        request_hash = canonical_request_digest(reconstructed_request)
        if (
            self.request_digest != request_hash
            or self.protocol_digest != protocol_hash
            or self.profile_digest != active_profile_hash
            or self.configuration_digest != config_hash
            or self.conformance_profile.protocol_schema_id != self.protocol_schema.schema_id
            or self.conformance_profile.protocol_schema_version != self.protocol_schema.version
            or self.conformance_profile.protocol_schema_digest != protocol_hash
        ):
            raise ValueError("result protocol and reviewed profile bindings are inconsistent")
        receipt = self.receipt
        expected_receipt = (
            protocol_hash,
            active_profile_hash,
            config_hash,
            protocol_section_digest(self.protocol_schema, "search_space"),
            protocol_section_digest(self.protocol_schema, "error_control"),
            protocol_section_digest(self.protocol_schema, "assignment"),
            protocol_section_digest(self.protocol_schema, "protein_grouping"),
            protocol_section_digest(self.protocol_schema, "ambiguity"),
            protocol_section_digest(self.protocol_schema, "complex_activity_handoff"),
        )
        actual_receipt = (
            receipt.protocol_digest,
            receipt.profile_digest,
            receipt.configuration_digest,
            receipt.search_space_digest,
            receipt.error_control_digest,
            receipt.assignment_digest,
            receipt.protein_group_digest,
            receipt.ambiguity_digest,
            receipt.handoff_digest,
        )
        if actual_receipt != expected_receipt:
            raise ValueError("protocol receipt contradicts embedded protocol material")
        sections = tuple(item.section for item in self.findings)
        if len(sections) != len(set(sections)) or set(sections) != set(ProtocolSection):
            raise ValueError("result requires exactly one finding for every protocol section")
        if {item.section: item for item in self.findings} != {
            item.section: item
            for item in expected_protocol_findings(
                self.protocol_schema,
                self.conformance_profile,
            )
        }:
            raise ValueError("result findings contradict embedded protocol and reviewed profile")
        states = {item.state for item in self.findings}
        expected_status = (
            ProtocolConformanceStatus.NONCONFORMANT
            if ProtocolFindingState.FAIL in states
            else (
                ProtocolConformanceStatus.INDETERMINATE
                if ProtocolFindingState.NOT_EVALUABLE in states
                else ProtocolConformanceStatus.CONFORMANT
            )
        )
        expected_disposition = (
            ProtocolConformanceDisposition.CONFORMANT
            if expected_status is ProtocolConformanceStatus.CONFORMANT
            else ProtocolConformanceDisposition.QUARANTINED
        )
        expected_support = (
            (
                SupportStatus.SUPPORTED,
                "protein_inference_protocol_conformant",
                M0301_CONFORMANT_SUPPORT_RATIONALE,
                False,
            )
            if expected_disposition is ProtocolConformanceDisposition.CONFORMANT
            else (
                SupportStatus.REVIEW_REQUIRED,
                "protein_inference_protocol_quarantined",
                M0301_QUARANTINED_SUPPORT_RATIONALE,
                True,
            )
        )
        if (
            self.status is not expected_status
            or self.disposition is not expected_disposition
            or receipt.disposition is not expected_disposition
            or (
                self.support.status,
                self.support.reason_code,
                self.support.rationale,
                self.human_review_required,
            )
            != expected_support
        ):
            raise ValueError("result disposition envelope contradicts its findings")
        provenance = self.provenance
        suffix = request_hash.removeprefix("sha256:")
        expected_controls = {
            ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
            ControlRole.IDENTITY_LINEAGE: "resolved",
            ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
            ControlRole.CONSENT: ConsentState.GRANTED.value,
            ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
            ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
            ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
        }
        controls = {item.role: item for item in provenance.control_decisions}
        references = self.context.references
        expected_control_records = {
            ControlRole.APPROVED_CONFIGURATION: (
                references.approved_configuration.decision_id,
                references.approved_configuration.state.value,
                references.approved_configuration.policy_version,
                references.approved_configuration.evidence.digest,
                None,
            ),
            ControlRole.IDENTITY_LINEAGE: (
                references.identity_lineage.decision_id,
                references.identity_lineage.state.value,
                references.identity_lineage.policy_version,
                references.identity_lineage.evidence.digest,
                references.identity_lineage.binding_digest,
            ),
            ControlRole.PROVENANCE: (
                references.provenance.decision_id,
                references.provenance.state.value,
                references.provenance.policy_version,
                references.provenance.evidence.digest,
                None,
            ),
            ControlRole.CONSENT: (
                references.consent.decision_id,
                references.consent.state.value,
                references.consent.policy_version,
                references.consent.evidence.digest,
                None,
            ),
            ControlRole.QUALITY: (
                references.quality.decision_id,
                references.quality.state.value,
                references.quality.policy_version,
                references.quality.evidence.digest,
                None,
            ),
            ControlRole.SUPPORT: (
                references.support.decision_id,
                references.support.state.value,
                references.support.policy_version,
                references.support.evidence.digest,
                None,
            ),
            ControlRole.INTENDED_USE: (
                references.intended_use.decision_id,
                references.intended_use.state.value,
                references.intended_use.policy_version,
                references.intended_use.evidence.digest,
                None,
            ),
        }
        actual_control_records = {
            role: (
                item.decision_id,
                item.state,
                item.policy_version,
                item.evidence_digest,
                item.subject_digest,
            )
            for role, item in controls.items()
        }
        required_inputs = {
            self.request_digest,
            protocol_hash,
            active_profile_hash,
            config_hash,
            *actual_receipt[3:],
            *(item.evidence_digest for item in controls.values()),
        }
        if (
            self.result_id != f"result.m0301.{suffix}"
            or provenance.activity_id != f"activity.m0301.{suffix}"
            or provenance.module_id != M0301_MODULE_ID
            or provenance.module_version != self.result_version
            or provenance.actor_id != self.context.actor_id
            or provenance.generated_at != self.completed_at
            or self.completed_at != self.context.occurred_at
            or provenance.configuration_digest != config_hash
            or provenance.consent_state is not ConsentState.GRANTED
            or {role: item.state for role, item in controls.items()} != expected_controls
            or actual_control_records != expected_control_records
            or provenance.consent_decision_id != references.consent.decision_id
            or provenance.consent_policy_version != references.consent.policy_version
            or provenance.consent_evidence_digest != references.consent.evidence.digest
            or set(provenance.input_digests) != required_inputs
            or len(provenance.input_digests) != len(required_inputs)
            or receipt.identity_subject_digest
            != controls[ControlRole.IDENTITY_LINEAGE].subject_digest
            or receipt.intended_use_evidence_digest
            != controls[ControlRole.INTENDED_USE].evidence_digest
        ):
            raise ValueError("result provenance and receipt envelope is inconsistent")
        expected_evidence = protocol_evidence_index(reconstructed_request)
        if tuple(sorted(self.evidence, key=lambda item: item.reference.digest)) != tuple(
            sorted(expected_evidence, key=lambda item: item.reference.digest)
        ):
            raise ValueError("result evidence index contradicts embedded protocol inputs")
        expected_limitations = {
            "protocol_conformance_only": (
                "This result validates a declared protein-inference protocol against one reviewed "
                "profile; it does not search spectra, assign peptides, infer proteins, or estimate "
                "error rates."
            ),
            "complex_activity_not_inferred": (
                "The complex-activity handoff contains protocol receipts and preserved ambiguity "
                "only; no complex, kinase, subtype, treatment, or clinical claim is produced."
            ),
        }
        if {item.code: item.statement for item in self.limitations} != expected_limitations:
            raise ValueError("result limitations exceed the M03-01 authority boundary")
        uncertainty_estimates = (
            self.uncertainty.measurement,
            self.uncertainty.sampling,
            self.uncertainty.parameter,
            self.uncertainty.model_form,
            self.uncertainty.identification,
            self.uncertainty.support,
            self.uncertainty.transport,
        )
        if tuple(
            (estimate.state, estimate.probability, estimate.rationale)
            for estimate in uncertainty_estimates
        ) != tuple(
            (EstimateState.NOT_ESTIMABLE, None, rationale)
            for rationale in M0301_UNCERTAINTY_RATIONALES
        ) or tuple(sorted(self.uncertainty.sensitivity_notes)) != tuple(
            sorted(M0301_SENSITIVITY_NOTES)
        ):
            raise ValueError("M03-01 uncertainty cannot claim calibrated estimates")
        expected_digest = result_payload_digest(self)
        if self.result_digest != expected_digest:
            raise ValueError("result digest does not match its canonical content")
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
        raise ValueError("protein-inference protocol evaluation is not authorized")


__all__ = [name for name in globals() if not name.startswith("_")]
