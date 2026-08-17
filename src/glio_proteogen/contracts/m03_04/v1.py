"""Strict M03-04 protein-inference evidence-graph quality contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m03_01 import (  # noqa: TC001 - Pydantic resolves models.
    DeclaredUnresolvedState,
    ProteinInferenceApplicability,
    SearchSpaceComposition,
    TargetDecoyStrategy,
)
from glio_proteogen.contracts.m03_02 import (
    ArtifactClaimRole,
    ReconciliationFindingCode,
)
from glio_proteogen.contracts.m03_03 import (
    M0303_MAX_DECODED_BYTES,
    M0303_MAX_SOURCE_BYTES,
    ProteinInferenceAdmissionDisposition,
    ProteinInferenceBuildBindingReceipt,
    ProteinInferenceBuildState,
    ProteinInferenceCompression,
    ProteinInferenceDiagnosticCode,
    ProteinInferenceRawAdmissionResult,
    ProteinInferenceRawFormat,
    ProteinInferenceRawRole,
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

M0304_MODULE_ID: Final = "GLIO-PROTEOGEN-M03-04"
M0304_OPERATION: Final = "compute_protein_inference_quality"
M0304_CONTRACT_VERSION: Final = "1.0.0"
M0304_PARENT: Final = "complex_activity"
M0304_OWNER: Final = "Clinical science"
M0304_SAFETY_CLASS: Final = "S2"
M0304_GATE: Final = "G1"
M0304_RATE_SCALE: Final = 1_000_000
M0304_MAX_SOURCES: Final = 64
M0304_MAX_SPECTRA_SOURCES: Final = 32
M0304_MAX_LINEAGE_ARTIFACTS: Final = 48
M0304_MAX_UPSTREAM_LINEAGE_ARTIFACTS: Final = 256
M0304_METRIC_COUNT: Final = 8
M0304_MAX_COUNT: Final = 10_000_000
M0304_MAX_FINDINGS: Final = 64 + (2 * 48) + (2 * 8) + 16
M0304_MAX_EVIDENCE: Final = 32
M0304_MAX_PROFILES: Final = 16
M0304_MAX_APPROVED_VERSIONS: Final = 32
M0304_MAX_CANONICAL_REQUEST_BYTES: Final = 2 * 1024 * 1024
M0304_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0304_QUALITY_LIMITATION_CODE: Final = "protein_inference_evidence_graph_quality_only"
M0304_AUTHORITY_LIMITATION_CODE: Final = "external_controls_not_authenticated"
M0304_EVIDENCE_CLAIM: Final = (
    "Caller-declared content-addressed M03-04 protein-inference quality evidence."
)
M0304_SENSITIVITY_NOTES: Final = (
    "Missing, unsupported, censored, and not-applicable facts remain explicitly typed.",
    "Threshold decisions are deterministic integer comparisons, not probabilities.",
)
M0304_UNCERTAINTY_RATIONALES: Final = (
    "Measurement uncertainty is not estimated from the compact quality fact ledger.",
    "Sampling uncertainty is not estimated by deterministic quality scoring.",
    "The deterministic threshold evaluator fits no parameters.",
    "No learned protein-inference or activity model is executed.",
    "Protein and proteoform identity remain outside this quality-only module.",
    "Support is a deterministic reviewed-threshold decision.",
    "Transportability requires external assay and reference validation.",
)


class ProteinInferenceQualityMetricCode(StrEnum):
    """Closed metadata-derived quality dimensions owned by M03-04."""

    ADMITTED_SOURCE_COMPLETENESS = "admitted_source_completeness"
    PEPTIDE_ASSIGNMENT_COVERAGE = "peptide_assignment_coverage"
    PROTEIN_GROUP_AMBIGUITY_BURDEN = "protein_group_ambiguity_burden"
    PROTEOFORM_DISCRIMINATION_COVERAGE = "proteoform_discrimination_coverage"
    PROTEIN_GROUP_DETECTION_SUPPORT = "protein_group_detection_support"
    PROTEIN_GROUP_COMPETITION_CLOSURE = "protein_group_competition_closure"
    CONTROL_GROUP_RECOVERY = "control_group_recovery"
    SAMPLE_CONTEXT_BINDING_COHERENCE = "sample_context_binding_coherence"


class ProteinInferenceQualityObservationState(StrEnum):
    OBSERVED = "observed"
    CENSORED = "censored"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class ProteinInferenceQualityMetricStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - domain status, not a credential.
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"
    NOT_APPLICABLE = "not_applicable"


class ProteinInferenceQualityMetricDirection(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"


class ProteinInferenceQualityDisposition(StrEnum):
    QUALIFIED = "qualified"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"
    REJECTED = "rejected"


class ProteinInferenceQualityFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"
    REJECT = "reject"


class ProteinInferenceQualityFindingCode(StrEnum):
    UPSTREAM_REJECTED = "upstream_rejected"
    UPSTREAM_QUARANTINED = "upstream_quarantined"
    UPSTREAM_ABSTAINED = "upstream_abstained"
    UPSTREAM_SHAPE_UNSUPPORTED = "upstream_shape_unsupported"
    FACT_LEDGER_BINDING_MISMATCH = "fact_ledger_binding_mismatch"
    ASSAY_PROFILE_UNSUPPORTED = "assay_profile_unsupported"
    REQUIRED_METRIC_MISSING = "required_metric_missing"
    REQUIRED_METRIC_UNSUPPORTED = "required_metric_unsupported"
    REQUIRED_METRIC_NOT_EVALUABLE = "required_metric_not_evaluable"
    REQUIRED_METRIC_WARNING = "required_metric_warning"
    METRIC_THRESHOLD_FAILED = "metric_threshold_failed"
    OPTIONAL_METRIC_WARNING = "optional_metric_warning"
    CROSS_METRIC_INCONSISTENCY = "cross_metric_inconsistency"


_DIRECTION_BY_METRIC: Final = {
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


_ACTION_BY_FINDING_CODE: Final = {
    ProteinInferenceQualityFindingCode.UPSTREAM_REJECTED: (
        ProteinInferenceQualityFindingAction.REJECT
    ),
    ProteinInferenceQualityFindingCode.UPSTREAM_QUARANTINED: (
        ProteinInferenceQualityFindingAction.QUARANTINE
    ),
    ProteinInferenceQualityFindingCode.UPSTREAM_ABSTAINED: (
        ProteinInferenceQualityFindingAction.ABSTAIN
    ),
    ProteinInferenceQualityFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        ProteinInferenceQualityFindingAction.ABSTAIN
    ),
    ProteinInferenceQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH: (
        ProteinInferenceQualityFindingAction.QUARANTINE
    ),
    ProteinInferenceQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED: (
        ProteinInferenceQualityFindingAction.ABSTAIN
    ),
    ProteinInferenceQualityFindingCode.REQUIRED_METRIC_MISSING: (
        ProteinInferenceQualityFindingAction.ABSTAIN
    ),
    ProteinInferenceQualityFindingCode.REQUIRED_METRIC_UNSUPPORTED: (
        ProteinInferenceQualityFindingAction.ABSTAIN
    ),
    ProteinInferenceQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE: (
        ProteinInferenceQualityFindingAction.ABSTAIN
    ),
    ProteinInferenceQualityFindingCode.REQUIRED_METRIC_WARNING: (
        ProteinInferenceQualityFindingAction.QUARANTINE
    ),
    ProteinInferenceQualityFindingCode.METRIC_THRESHOLD_FAILED: (
        ProteinInferenceQualityFindingAction.QUARANTINE
    ),
    ProteinInferenceQualityFindingCode.OPTIONAL_METRIC_WARNING: (
        ProteinInferenceQualityFindingAction.RECORD
    ),
    ProteinInferenceQualityFindingCode.CROSS_METRIC_INCONSISTENCY: (
        ProteinInferenceQualityFindingAction.QUARANTINE
    ),
}

_MESSAGE_BY_FINDING_CODE: Final = {
    ProteinInferenceQualityFindingCode.UPSTREAM_REJECTED: (
        "M03-03 rejected the raw-admission result."
    ),
    ProteinInferenceQualityFindingCode.UPSTREAM_QUARANTINED: (
        "M03-03 quarantined the raw-admission result."
    ),
    ProteinInferenceQualityFindingCode.UPSTREAM_ABSTAINED: (
        "M03-03 abstained from raw-input admission."
    ),
    ProteinInferenceQualityFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        "The upstream lineage shape exceeds the reviewed M03-04 compute envelope."
    ),
    ProteinInferenceQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH: (
        "The fact ledger does not bind the exact compact M03-03 receipt."
    ),
    ProteinInferenceQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED: (
        "No reviewed quality profile applies to the declared assay metadata."
    ),
    ProteinInferenceQualityFindingCode.REQUIRED_METRIC_MISSING: (
        "A required quality metric is missing."
    ),
    ProteinInferenceQualityFindingCode.REQUIRED_METRIC_UNSUPPORTED: (
        "A required quality metric is unsupported."
    ),
    ProteinInferenceQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE: (
        "A required quality metric is not evaluable."
    ),
    ProteinInferenceQualityFindingCode.REQUIRED_METRIC_WARNING: (
        "A required quality metric reached its warning band."
    ),
    ProteinInferenceQualityFindingCode.METRIC_THRESHOLD_FAILED: (
        "A quality metric failed its reviewed threshold."
    ),
    ProteinInferenceQualityFindingCode.OPTIONAL_METRIC_WARNING: (
        "An optional quality metric reached its warning band."
    ),
    ProteinInferenceQualityFindingCode.CROSS_METRIC_INCONSISTENCY: (
        "The quality metrics contradict the closed fact partitions."
    ),
}

_RAW_ROLE_BY_CLAIM_ROLE: Final = {
    ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST: ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
    ArtifactClaimRole.PROTEIN_GROUP_MANIFEST: ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
    ArtifactClaimRole.AMBIGUITY_MANIFEST: ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
    ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE: (
        ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE
    ),
}

_RAW_FORMAT_BY_ROLE: Final = {
    ProteinInferenceRawRole.SPECTRA: ProteinInferenceRawFormat.MZML,
    ProteinInferenceRawRole.PEPTIDE_EVIDENCE: ProteinInferenceRawFormat.MZIDENTML,
    ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST: ProteinInferenceRawFormat.PROTEIN_GROUP_JSON,
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


class ProteinInferenceQualityThreshold(FrozenModel):
    metric_code: ProteinInferenceQualityMetricCode
    direction: ProteinInferenceQualityMetricDirection
    pass_threshold_ppm: int = Field(ge=0, le=M0304_RATE_SCALE)
    warning_threshold_ppm: int = Field(ge=0, le=M0304_RATE_SCALE)
    required: bool
    evidence: ArtifactReference

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> ProteinInferenceQualityThreshold:
        if self.direction is not _DIRECTION_BY_METRIC[self.metric_code]:
            raise ValueError("quality threshold direction contradicts its metric")
        if (
            self.direction is ProteinInferenceQualityMetricDirection.AT_LEAST
            and self.warning_threshold_ppm > self.pass_threshold_ppm
        ) or (
            self.direction is ProteinInferenceQualityMetricDirection.AT_MOST
            and self.warning_threshold_ppm < self.pass_threshold_ppm
        ):
            raise ValueError("quality warning and pass thresholds are directionally invalid")
        return self


class ProteinInferenceAssayQualityProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    applicability: ProteinInferenceApplicability
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0304_MAX_APPROVED_VERSIONS
    )
    approved_controlled_vocabulary_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0304_MAX_APPROVED_VERSIONS
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0304_MAX_APPROVED_VERSIONS
    )
    controls_applicable: bool
    thresholds: tuple[ProteinInferenceQualityThreshold, ...] = Field(
        min_length=M0304_METRIC_COUNT,
        max_length=M0304_METRIC_COUNT,
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
        values: tuple[ProteinInferenceQualityThreshold, ...],
    ) -> tuple[ProteinInferenceQualityThreshold, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def profile_is_closed(self) -> ProteinInferenceAssayQualityProfile:
        version_sets = (
            self.approved_assay_protocol_versions,
            self.approved_controlled_vocabulary_versions,
            self.approved_unit_system_versions,
        )
        if any(len(values) != len(set(values)) for values in version_sets):
            raise ValueError("approved profile versions must be unique")
        codes = tuple(item.metric_code for item in self.thresholds)
        if len(codes) != len(set(codes)) or set(codes) != set(ProteinInferenceQualityMetricCode):
            raise ValueError("quality profile requires each of the eight metrics exactly once")
        return self


class ProteinInferenceQualityPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_sources: int = Field(gt=0, le=M0304_MAX_SOURCES)
    max_lineage_artifacts: int = Field(ge=4, le=M0304_MAX_LINEAGE_ARTIFACTS)
    profiles: tuple[ProteinInferenceAssayQualityProfile, ...] = Field(
        min_length=1,
        max_length=M0304_MAX_PROFILES,
    )
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("profiles")
    @classmethod
    def profiles_are_canonical(
        cls,
        values: tuple[ProteinInferenceAssayQualityProfile, ...],
    ) -> tuple[ProteinInferenceAssayQualityProfile, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def policy_profiles_are_unambiguous(self) -> ProteinInferenceQualityPolicy:
        identities = tuple((item.profile_id, item.version) for item in self.profiles)
        if len(identities) != len(set(identities)):
            raise ValueError("quality policy profile identities must be unique")
        for index, left in enumerate(self.profiles):
            for right in self.profiles[index + 1 :]:
                overlapping_domain = (
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
                if overlapping_domain:
                    raise ValueError("quality policy profile match domains must be disjoint")
        return self


class ProteinInferenceRawQualitySourceReceipt(FrozenModel):
    source_id: Identifier
    role: ProteinInferenceRawRole
    bound_claim_id: Identifier | None = None
    artifact_digest: Sha256Digest
    source_digest: Sha256Digest
    source_size_bytes: int = Field(ge=0, le=M0303_MAX_SOURCE_BYTES + 1)
    decoded_digest: Sha256Digest | None = None
    decoded_size_bytes: int = Field(ge=0, le=M0303_MAX_DECODED_BYTES + 1)
    detected_format: ProteinInferenceRawFormat | None = None
    detected_version: SemanticVersion | None = None
    compression: ProteinInferenceCompression | None = None
    record_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    reference_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    build: ProteinInferenceBuildBindingReceipt
    diagnostic_codes: tuple[ProteinInferenceDiagnosticCode, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def source_projection_is_closed(self) -> ProteinInferenceRawQualitySourceReceipt:
        if len(self.diagnostic_codes) != len(set(self.diagnostic_codes)):
            raise ValueError("projected source diagnostic codes must be unique")
        decoded_cap = (
            ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED in self.diagnostic_codes
        )
        raw_cap = ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED in (self.diagnostic_codes)
        if self.decoded_digest is None and self.decoded_size_bytes != 0 and not decoded_cap:
            raise ValueError("decoded byte count requires a decoded digest")
        if decoded_cap and self.decoded_digest is not None:
            raise ValueError("bounded partial decode cannot claim a complete decoded digest")
        if self.decoded_size_bytes > M0303_MAX_DECODED_BYTES and not decoded_cap:
            raise ValueError("decoded size overflow must carry its exact diagnostic")
        if self.source_size_bytes > M0303_MAX_SOURCE_BYTES and not raw_cap:
            raise ValueError("source size overflow must carry its exact diagnostic")
        if self.detected_format is None and self.detected_version is not None:
            raise ValueError("detected version requires a detected format")
        return self


class ProteinInferenceRawQualityClaimReceipt(FrozenModel):
    claim_id: Identifier
    claim_role: ArtifactClaimRole
    artifact_digest: Sha256Digest
    lineage_path_digest: Sha256Digest
    evidence_state: Literal["observed"] | DeclaredUnresolvedState
    finding_codes: tuple[ReconciliationFindingCode, ...] = Field(default=(), max_length=16)

    @field_validator("finding_codes")
    @classmethod
    def finding_codes_are_unique(
        cls,
        values: tuple[ReconciliationFindingCode, ...],
    ) -> tuple[ReconciliationFindingCode, ...]:
        if len(values) != len(set(values)):
            raise ValueError("projected claim finding codes must be unique")
        return values


class ProteinInferenceRawQualityReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = M0304_CONTRACT_VERSION
    admission_result_digest: Sha256Digest
    admission_request_digest: Sha256Digest
    admission_policy_digest: Sha256Digest
    admission_configuration_digest: Sha256Digest
    protocol_receipt_digest: Sha256Digest
    lineage_receipt_digest: Sha256Digest
    source_manifest_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    protocol_digest: Sha256Digest
    search_space_digest: Sha256Digest
    identity_subject_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    lineage_result_digest: Sha256Digest
    lineage_graph_digest: Sha256Digest
    upstream_disposition: ProteinInferenceAdmissionDisposition
    upstream_support_status: SupportStatus
    upstream_human_review_required: bool
    upstream_completed_at: AwareDatetime
    assay_protocol_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    search_space_build_id: Identifier
    search_space_release: SemanticVersion
    target_decoy_strategy: TargetDecoyStrategy
    search_space_composition: SearchSpaceComposition
    source_count: int = Field(ge=0, le=M0304_MAX_SOURCES)
    lineage_artifact_count: int = Field(
        ge=4,
        le=M0304_MAX_UPSTREAM_LINEAGE_ARTIFACTS,
    )
    sources: tuple[ProteinInferenceRawQualitySourceReceipt, ...] = Field(
        default=(), max_length=M0304_MAX_SOURCES
    )
    claims: tuple[ProteinInferenceRawQualityClaimReceipt, ...] = Field(
        default=(), max_length=M0304_MAX_LINEAGE_ARTIFACTS
    )
    receipt_digest: Sha256Digest

    @field_validator("sources", "claims")
    @classmethod
    def receipt_projections_are_canonical(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_is_exact_and_content_addressed(  # noqa: PLR0912 - explicit handoff closure.
        self,
    ) -> ProteinInferenceRawQualityReceipt:
        source_ids = tuple(item.source_id for item in self.sources)
        claim_ids = tuple(item.claim_id for item in self.claims)
        if len(source_ids) != len(set(source_ids)) or len(claim_ids) != len(set(claim_ids)):
            raise ValueError("quality receipt projections require unique identifiers")
        if self.identity_subject_digest != self.identity_resolution_digest:
            raise ValueError("quality receipt identity subject and resolution do not close")
        expected_support, expected_review = {
            ProteinInferenceAdmissionDisposition.VALIDATED: (SupportStatus.SUPPORTED, False),
            ProteinInferenceAdmissionDisposition.QUARANTINED: (
                SupportStatus.REVIEW_REQUIRED,
                True,
            ),
            ProteinInferenceAdmissionDisposition.ABSTAINED: (
                SupportStatus.UNSUPPORTED,
                True,
            ),
            ProteinInferenceAdmissionDisposition.REJECTED: (
                SupportStatus.UNSUPPORTED,
                True,
            ),
        }[self.upstream_disposition]
        if (
            self.upstream_support_status is not expected_support
            or self.upstream_human_review_required != expected_review
        ):
            raise ValueError("M03-03 disposition, support, and review envelope contradict")
        traversable = (
            self.upstream_disposition is ProteinInferenceAdmissionDisposition.VALIDATED
            and self.lineage_artifact_count <= M0304_MAX_LINEAGE_ARTIFACTS
        )
        if traversable:
            if self.source_count != len(self.sources) or self.lineage_artifact_count != len(
                self.claims
            ):
                raise ValueError("validated quality receipt projections must be complete")
            bound = tuple(
                item.bound_claim_id for item in self.sources if item.bound_claim_id is not None
            )
            if len(bound) != len(set(bound)) or set(bound) != set(claim_ids):
                raise ValueError("quality source and claim projections do not close")
            claims_by_id = {item.claim_id: item for item in self.claims}
            _validate_quality_receipt_role_shape(self)
            if any(item.evidence_state != "observed" or item.finding_codes for item in self.claims):
                raise ValueError("validated quality claims must preserve observed clean lineage")
            for source in self.sources:
                if (
                    source.artifact_digest != source.source_digest
                    or source.detected_format is not _RAW_FORMAT_BY_ROLE[source.role]
                    or source.compression is None
                    or source.diagnostic_codes
                    or source.build.state
                    not in {
                        ProteinInferenceBuildState.EXACT,
                        ProteinInferenceBuildState.NOT_APPLICABLE,
                    }
                ):
                    raise ValueError("validated quality source projection is not exact")
                if source.bound_claim_id is None:
                    continue
                claim = claims_by_id[source.bound_claim_id]
                if (
                    source.role is not _RAW_ROLE_BY_CLAIM_ROLE[claim.claim_role]
                    or source.artifact_digest != claim.artifact_digest
                ):
                    raise ValueError("quality source contradicts its bound lineage claim")
        elif self.sources or self.claims:
            raise ValueError("safe-failure quality receipts cannot expose source or claim rows")
        from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
            raw_quality_receipt_digest,
        )

        if self.receipt_digest != raw_quality_receipt_digest(self):
            raise ValueError("M03-04 raw-quality receipt digest does not match its content")
        return self


def _validate_quality_receipt_role_shape(receipt: ProteinInferenceRawQualityReceipt) -> None:
    roles = tuple(item.role for item in receipt.sources)
    role_counts = {role: roles.count(role) for role in ProteinInferenceRawRole}
    if not 1 <= role_counts[ProteinInferenceRawRole.SPECTRA] <= M0304_MAX_SPECTRA_SOURCES:
        raise ValueError("quality receipt requires a bounded nonempty spectra source set")
    exact_source_roles = {
        ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
        ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
        ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
        ProteinInferenceRawRole.CANONICAL_SEQUENCES,
        ProteinInferenceRawRole.DECOY_SEQUENCES,
        ProteinInferenceRawRole.PTM_VOCABULARY,
    }
    if any(role_counts[role] != 1 for role in exact_source_roles):
        raise ValueError("quality receipt required source roles must occur exactly once")
    peptide_claim_count = tuple(item.claim_role for item in receipt.claims).count(
        ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST
    )
    if role_counts[ProteinInferenceRawRole.PEPTIDE_EVIDENCE] != peptide_claim_count:
        raise ValueError("quality receipt peptide sources and claims must have equal count")
    composition = receipt.search_space_composition
    conditional = (
        (ProteinInferenceRawRole.ISOFORM_SEQUENCES, composition.isoform_sequences),
        (ProteinInferenceRawRole.VARIANT_SEQUENCES, composition.variant_sequences),
        (ProteinInferenceRawRole.CONTAMINANT_SEQUENCES, composition.contaminant_sequences),
    )
    if any(role_counts[role] != int(count > 0) for role, count in conditional):
        raise ValueError("quality receipt conditional source roles contradict search space")
    for role, required_count in (
        (ProteinInferenceRawRole.GENOMIC_CONTEXT, composition.variant_sequences),
        (ProteinInferenceRawRole.TRANSCRIPT_CONTEXT, composition.isoform_sequences),
    ):
        count = role_counts[role]
        if count > 1 or (required_count > 0 and count != 1):
            raise ValueError("quality receipt context roles contradict governed search space")
    claim_roles = tuple(item.claim_role for item in receipt.claims)
    if (
        claim_roles.count(ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST) < 1
        or claim_roles.count(ArtifactClaimRole.PROTEIN_GROUP_MANIFEST) != 1
        or claim_roles.count(ArtifactClaimRole.AMBIGUITY_MANIFEST) != 1
        or claim_roles.count(ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE) != 1
    ):
        raise ValueError("quality receipt claims contradict the exact lineage role shape")
    peptides = tuple(
        item for item in receipt.sources if item.role is ProteinInferenceRawRole.PEPTIDE_EVIDENCE
    )
    ptm = next(
        item for item in receipt.sources if item.role is ProteinInferenceRawRole.PTM_VOCABULARY
    )
    if any(
        (item.build.declared_build_id, item.build.declared_build_version)
        != (receipt.search_space_build_id, receipt.search_space_release)
        for item in peptides
    ):
        raise ValueError("peptide source build does not bind the exact search space")
    if (ptm.build.declared_build_id, ptm.build.declared_build_version) != (
        receipt.controlled_vocabulary_id,
        receipt.controlled_vocabulary_version,
    ):
        raise ValueError("PTM source build does not bind the exact controlled vocabulary")


class ProteinInferenceQualityCounts(FrozenModel):
    eligible_peptide_evidence_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    unique_assigned_peptide_evidence_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    shared_group_assigned_peptide_evidence_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    unassigned_peptide_evidence_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    total_group_member_assignment_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    ambiguous_group_member_assignment_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    eligible_proteoform_claim_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    discriminating_proteoform_claim_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    detection_eligible_group_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    quantifiable_group_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    left_censored_group_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    detection_missing_group_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    competition_eligible_group_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    competition_closed_group_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    control_expected_group_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    control_recovered_group_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    context_applicable_binding_count: int = Field(ge=0, le=M0304_MAX_COUNT)
    context_coherent_binding_count: int = Field(ge=0, le=M0304_MAX_COUNT)

    @model_validator(mode="after")
    def count_partitions_close(self) -> ProteinInferenceQualityCounts:
        if (
            self.unique_assigned_peptide_evidence_count
            + self.shared_group_assigned_peptide_evidence_count
            + self.unassigned_peptide_evidence_count
            != self.eligible_peptide_evidence_count
        ):
            raise ValueError("peptide assignment counts must partition eligible evidence")
        if (
            self.ambiguous_group_member_assignment_count > self.total_group_member_assignment_count
            or self.discriminating_proteoform_claim_count > self.eligible_proteoform_claim_count
        ):
            raise ValueError("quality numerator cannot exceed its eligible denominator")
        if (
            self.quantifiable_group_count
            + self.left_censored_group_count
            + self.detection_missing_group_count
            != self.detection_eligible_group_count
        ):
            raise ValueError("detection-support counts must partition eligible groups")
        if (
            self.competition_closed_group_count > self.competition_eligible_group_count
            or self.control_recovered_group_count > self.control_expected_group_count
            or self.context_coherent_binding_count > self.context_applicable_binding_count
        ):
            raise ValueError("quality numerator cannot exceed its eligible denominator")
        return self


class ProteinInferenceQualityFactStates(FrozenModel):
    peptide_assignment: ProteinInferenceQualityObservationState
    ambiguity_burden: ProteinInferenceQualityObservationState
    proteoform_discrimination: ProteinInferenceQualityObservationState
    detection_support: ProteinInferenceQualityObservationState
    competition_closure: ProteinInferenceQualityObservationState
    control_recovery: ProteinInferenceQualityObservationState
    sample_context_coherence: ProteinInferenceQualityObservationState

    @model_validator(mode="after")
    def censored_state_is_detection_only(self) -> ProteinInferenceQualityFactStates:
        values = (
            self.peptide_assignment,
            self.ambiguity_burden,
            self.proteoform_discrimination,
            self.competition_closure,
            self.control_recovery,
            self.sample_context_coherence,
        )
        if ProteinInferenceQualityObservationState.CENSORED in values:
            raise ValueError("only detection support may carry a censored fact state")
        return self


class ProteinInferenceQualityFactLedger(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    admission_result_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    search_space_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    source_manifest_digest: Sha256Digest
    applicability: ProteinInferenceApplicability
    source_binding_digest: Sha256Digest
    claim_binding_digest: Sha256Digest
    states: ProteinInferenceQualityFactStates
    counts: ProteinInferenceQualityCounts
    evidence: ArtifactReference
    recorded_at: AwareDatetime
    ledger_digest: Sha256Digest

    @model_validator(mode="after")
    def ledger_states_and_digest_close(self) -> ProteinInferenceQualityFactLedger:
        c = self.counts
        s = self.states
        partitions = (
            (
                s.peptide_assignment,
                (
                    c.eligible_peptide_evidence_count,
                    c.unique_assigned_peptide_evidence_count,
                    c.shared_group_assigned_peptide_evidence_count,
                    c.unassigned_peptide_evidence_count,
                ),
            ),
            (
                s.ambiguity_burden,
                (
                    c.total_group_member_assignment_count,
                    c.ambiguous_group_member_assignment_count,
                ),
            ),
            (
                s.proteoform_discrimination,
                (
                    c.eligible_proteoform_claim_count,
                    c.discriminating_proteoform_claim_count,
                ),
            ),
            (
                s.competition_closure,
                (c.competition_eligible_group_count, c.competition_closed_group_count),
            ),
            (
                s.control_recovery,
                (c.control_expected_group_count, c.control_recovered_group_count),
            ),
            (
                s.sample_context_coherence,
                (c.context_applicable_binding_count, c.context_coherent_binding_count),
            ),
        )
        for state, counts in partitions:
            if state is not ProteinInferenceQualityObservationState.OBSERVED and any(counts):
                raise ValueError("non-observed fact partitions must contain only zero counts")
        detection_counts = (
            c.detection_eligible_group_count,
            c.quantifiable_group_count,
            c.left_censored_group_count,
            c.detection_missing_group_count,
        )
        if s.detection_support not in {
            ProteinInferenceQualityObservationState.OBSERVED,
            ProteinInferenceQualityObservationState.CENSORED,
        } and any(detection_counts):
            raise ValueError("non-observed detection facts must contain only zero counts")
        if (
            s.detection_support is ProteinInferenceQualityObservationState.CENSORED
            and c.detection_missing_group_count != 0
        ):
            raise ValueError("censored detection facts cannot also count missing groups")
        if (s.detection_support is ProteinInferenceQualityObservationState.CENSORED) != (
            c.left_censored_group_count > 0
        ):
            raise ValueError("detection censoring state must match its censored count")
        from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
            fact_ledger_digest,
        )

        if self.ledger_digest != fact_ledger_digest(self):
            raise ValueError("M03-04 fact-ledger digest does not match its content")
        return self


class ComputeProteinInferenceQualityRequest(FrozenModel):
    operation: Literal["compute_protein_inference_quality"] = M0304_OPERATION
    contract_version: Literal["1.0.0"] = M0304_CONTRACT_VERSION
    context: ExecutionContext
    raw_quality_receipt: ProteinInferenceRawQualityReceipt
    fact_ledger: ProteinInferenceQualityFactLedger | None = None
    policy: ProteinInferenceQualityPolicy
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_and_closed(self) -> ComputeProteinInferenceQualityRequest:
        _require_authorized_context(self.context)
        receipt = self.raw_quality_receipt
        ledger = self.fact_ledger
        if max(receipt.upstream_completed_at, self.policy.reviewed_at) > self.context.occurred_at:
            raise ValueError("M03-04 inputs cannot postdate quality computation")
        if self.context.references.identity_lineage.binding_digest != (
            receipt.identity_resolution_digest
        ):
            raise ValueError("identity control does not bind the M03-03 identity receipt")
        from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
            configuration_digest,
        )

        if self.context.references.approved_configuration.evidence.digest != (
            configuration_digest(self.policy)
        ):
            raise ValueError("approved configuration does not bind the M03-04 policy")
        traversable = (
            receipt.upstream_disposition is ProteinInferenceAdmissionDisposition.VALIDATED
            and receipt.lineage_artifact_count <= self.policy.max_lineage_artifacts
            and receipt.source_count <= self.policy.max_sources
        )
        if traversable != (ledger is not None):
            raise ValueError("fact-ledger presence contradicts the safe traversal envelope")
        if ledger is not None and not (
            receipt.upstream_completed_at <= ledger.recorded_at <= self.context.occurred_at
        ):
            raise ValueError("quality facts must follow M03-03 and precede computation")
        if len(canonical_json_bytes(self.model_dump(mode="python"))) > (
            M0304_MAX_CANONICAL_REQUEST_BYTES
        ):
            raise ValueError("canonical M03-04 request exceeds its ingress ceiling")
        return self


class ProteinInferenceQualityMetricProvenance(FrozenModel):
    admission_result_digest: Sha256Digest
    fact_ledger_digest: Sha256Digest
    profile_digest: Sha256Digest
    threshold_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    claim_binding_digest: Sha256Digest


class ProteinInferenceQualityMetricResult(FrozenModel):
    metric_code: ProteinInferenceQualityMetricCode
    observation_state: ProteinInferenceQualityObservationState
    status: ProteinInferenceQualityMetricStatus
    required: bool
    numerator: int | None = Field(default=None, ge=0, le=M0304_MAX_COUNT)
    denominator: int | None = Field(default=None, ge=0, le=M0304_MAX_COUNT)
    value_ppm: int | None = Field(default=None, ge=0, le=M0304_RATE_SCALE)
    unit: Literal["ppm_fraction"] = "ppm_fraction"
    censored_count: int = Field(default=0, ge=0, le=M0304_MAX_COUNT)
    provenance: ProteinInferenceQualityMetricProvenance

    @model_validator(mode="after")
    def metric_shape_is_exact(self) -> ProteinInferenceQualityMetricResult:
        no_value_states = {
            ProteinInferenceQualityObservationState.MISSING,
            ProteinInferenceQualityObservationState.NOT_APPLICABLE,
            ProteinInferenceQualityObservationState.UNSUPPORTED,
        }
        if self.observation_state in no_value_states:
            if any(item is not None for item in (self.numerator, self.denominator, self.value_ppm)):
                raise ValueError("non-observed quality states cannot carry a ratio")
            expected = (
                ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
                if self.observation_state is ProteinInferenceQualityObservationState.NOT_APPLICABLE
                else ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
            )
            if self.status is not expected or self.censored_count != 0:
                raise ValueError("non-observed quality state has an invalid status")
            return self
        if self.numerator is None or self.denominator is None:
            raise ValueError("observed quality metrics require numerator and denominator")
        if self.numerator > self.denominator:
            raise ValueError("quality numerator cannot exceed its denominator")
        if self.censored_count > self.denominator:
            raise ValueError("censored count cannot exceed its metric denominator")
        if self.denominator == 0:
            if (
                self.numerator != 0
                or self.value_ppm is not None
                or (self.status is not ProteinInferenceQualityMetricStatus.NOT_EVALUABLE)
            ):
                raise ValueError("zero-denominator metric must remain explicitly not evaluable")
        else:
            expected_value = (
                self.numerator * M0304_RATE_SCALE + self.denominator // 2
            ) // self.denominator
            if self.value_ppm != expected_value or self.status in {
                ProteinInferenceQualityMetricStatus.NOT_EVALUABLE,
                ProteinInferenceQualityMetricStatus.NOT_APPLICABLE,
            }:
                raise ValueError("quality value does not match the exact integer ratio")
        if (self.observation_state is ProteinInferenceQualityObservationState.CENSORED) != (
            self.censored_count > 0
        ):
            raise ValueError("censored observation state requires a positive censored count")
        return self


class ProteinInferenceQualityFinding(FrozenModel):
    finding_id: Identifier
    code: ProteinInferenceQualityFindingCode
    action: ProteinInferenceQualityFindingAction
    metric_codes: tuple[ProteinInferenceQualityMetricCode, ...] = Field(
        default=(), max_length=M0304_METRIC_COUNT
    )
    source_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0304_MAX_SOURCES)
    claim_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0304_MAX_LINEAGE_ARTIFACTS)
    message: NonEmptyStr

    @model_validator(mode="after")
    def finding_is_closed(self) -> ProteinInferenceQualityFinding:
        dimensions = (self.metric_codes, self.source_ids, self.claim_ids)
        if any(len(values) != len(set(values)) for values in dimensions):
            raise ValueError("quality finding references must be unique")
        expected = finding_for(
            self.code,
            metric_codes=self.metric_codes,
            source_ids=self.source_ids,
            claim_ids=self.claim_ids,
        )
        if self != expected:
            raise ValueError("M03-04 finding contradicts its closed vocabulary")
        return self


class ProteinInferenceQualityComputationReceipt(FrozenModel):
    raw_quality_receipt_digest: Sha256Digest
    fact_ledger_digest: Sha256Digest | None = None
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    profile_digest: Sha256Digest | None = None
    parent_target: Literal["complex_activity"] = M0304_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    disposition: ProteinInferenceQualityDisposition


class ProteinInferenceQualityResult(NonInferenceResultModel):
    output_type: Literal["protein_inference_quality_profile"] = "protein_inference_quality_profile"
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0304_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ComputeProteinInferenceQualityRequest
    receipt: ProteinInferenceQualityComputationReceipt
    metrics: tuple[ProteinInferenceQualityMetricResult, ...] = Field(
        default=(), max_length=M0304_METRIC_COUNT
    )
    findings: tuple[ProteinInferenceQualityFinding, ...] = Field(
        default=(), max_length=M0304_MAX_FINDINGS
    )
    disposition: ProteinInferenceQualityDisposition
    parent_target: Literal["complex_activity"] = M0304_PARENT
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0304_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("metrics", "findings", "evidence", "limitations")
    @classmethod
    def semantic_result_collections_are_canonical(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
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
    ) -> ProteinInferenceQualityResult:
        from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
            canonical_request_digest,
            configuration_digest,
            policy_digest,
            result_payload_digest,
        )

        metric_codes = tuple(item.metric_code for item in self.metrics)
        if len(metric_codes) != len(set(metric_codes)):
            raise ValueError("M03-04 result metric codes must be unique")
        safe_failure = (
            self.request.fact_ledger is None
            or not _ledger_bindings_close(self.request)
            or _matching_profile(self.request) is None
        )
        if safe_failure:
            if self.metrics:
                raise ValueError("safe-failure quality results cannot carry metrics")
        elif len(self.metrics) != M0304_METRIC_COUNT or set(metric_codes) != set(
            ProteinInferenceQualityMetricCode
        ):
            raise ValueError("traversed quality results require all eight exact metrics")
        if not safe_failure:
            _validate_metric_replay(self.request, self.metrics)
        expected_findings = expected_quality_findings(self.request, self.metrics)
        if tuple(sorted(self.findings, key=canonical_json_bytes)) != expected_findings:
            raise ValueError("M03-04 result findings do not replay from request and metrics")
        disposition = expected_disposition(self.request, self.metrics, self.findings)
        expected_receipt = expected_computation_receipt(
            self.request,
            disposition,
            _matching_profile(self.request),
        )
        request_hash = canonical_request_digest(self.request)
        policy_hash = policy_digest(self.request.policy)
        config_hash = configuration_digest(self.request.policy)
        if (
            self.result_id != f"result.m0304.{request_hash.removeprefix('sha256:')}"
            or self.request_digest != request_hash
            or self.policy_digest != policy_hash
            or self.configuration_digest != config_hash
            or self.receipt != expected_receipt
            or self.disposition is not disposition
        ):
            raise ValueError("M03-04 result envelope contradicts its replayed request")
        if self.completed_at != self.request.context.occurred_at:
            raise ValueError("M03-04 result completion time must equal execution time")
        if self.support != expected_support(disposition, self.metrics):
            raise ValueError("M03-04 result support is not deterministic")
        if not _uncertainty_equal(self.uncertainty, expected_uncertainty(disposition)):
            raise ValueError("M03-04 result uncertainty is not deterministic")
        if not _provenance_equal(
            self.provenance,
            expected_provenance(self.request, disposition),
        ):
            raise ValueError("M03-04 result provenance does not close")
        if not _semantic_tuple_equal(self.evidence, quality_evidence_index(self.request)):
            raise ValueError("M03-04 result evidence index does not close")
        if not _semantic_tuple_equal(self.limitations, expected_limitations()):
            raise ValueError("M03-04 result limitations do not close")
        optional_warning = any(
            item.status is ProteinInferenceQualityMetricStatus.WARNING and not item.required
            for item in self.metrics
        )
        expected_review = disposition is not ProteinInferenceQualityDisposition.QUALIFIED or (
            optional_warning
        )
        if self.human_review_required != expected_review:
            raise ValueError("M03-04 human-review flag contradicts quality disposition")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("M03-04 result digest does not match its payload")
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


def _require_authorized_context(context: ExecutionContext) -> None:
    refs = context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize M03-04 quality computation")
    generic = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic):
        raise ValueError("every generic control must accept M03-04 quality computation")
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before M03-04 computation")


def _matching_profile(
    request: ComputeProteinInferenceQualityRequest,
) -> ProteinInferenceAssayQualityProfile | None:
    ledger = request.fact_ledger
    receipt = request.raw_quality_receipt
    if ledger is None:
        return None
    return next(
        (
            profile
            for profile in request.policy.profiles
            if profile.applicability is ledger.applicability
            and receipt.assay_protocol_version in profile.approved_assay_protocol_versions
            and receipt.controlled_vocabulary_version
            in profile.approved_controlled_vocabulary_versions
            and receipt.unit_system_version in profile.approved_unit_system_versions
        ),
        None,
    )


def _metric_facts(
    request: ComputeProteinInferenceQualityRequest,
) -> dict[
    ProteinInferenceQualityMetricCode,
    tuple[ProteinInferenceQualityObservationState, int, int, int],
]:
    ledger = request.fact_ledger
    if ledger is None:
        return {}
    receipt = request.raw_quality_receipt
    counts = ledger.counts
    states = ledger.states
    return {
        ProteinInferenceQualityMetricCode.ADMITTED_SOURCE_COMPLETENESS: (
            ProteinInferenceQualityObservationState.OBSERVED,
            len(receipt.sources),
            receipt.source_count,
            0,
        ),
        ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE: (
            states.peptide_assignment,
            counts.unique_assigned_peptide_evidence_count
            + counts.shared_group_assigned_peptide_evidence_count,
            counts.eligible_peptide_evidence_count,
            0,
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN: (
            states.ambiguity_burden,
            counts.ambiguous_group_member_assignment_count,
            counts.total_group_member_assignment_count,
            0,
        ),
        ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE: (
            states.proteoform_discrimination,
            counts.discriminating_proteoform_claim_count,
            counts.eligible_proteoform_claim_count,
            0,
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT: (
            states.detection_support,
            counts.quantifiable_group_count,
            counts.detection_eligible_group_count,
            counts.left_censored_group_count,
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_COMPETITION_CLOSURE: (
            states.competition_closure,
            counts.competition_closed_group_count,
            counts.competition_eligible_group_count,
            0,
        ),
        ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY: (
            states.control_recovery,
            counts.control_recovered_group_count,
            counts.control_expected_group_count,
            0,
        ),
        ProteinInferenceQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE: (
            states.sample_context_coherence,
            counts.context_coherent_binding_count,
            counts.context_applicable_binding_count,
            0,
        ),
    }


def _status_for_ratio(  # noqa: PLR0911 - closed threshold matrix.
    numerator: int,
    denominator: int,
    threshold: ProteinInferenceQualityThreshold,
) -> ProteinInferenceQualityMetricStatus:
    if denominator == 0:
        return ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
    pass_product = threshold.pass_threshold_ppm * denominator
    warning_product = threshold.warning_threshold_ppm * denominator
    value_product = numerator * M0304_RATE_SCALE
    if threshold.direction is ProteinInferenceQualityMetricDirection.AT_LEAST:
        if value_product >= pass_product:
            return ProteinInferenceQualityMetricStatus.PASS
        if value_product >= warning_product:
            return ProteinInferenceQualityMetricStatus.WARNING
        return ProteinInferenceQualityMetricStatus.FAIL
    if value_product <= pass_product:
        return ProteinInferenceQualityMetricStatus.PASS
    if value_product <= warning_product:
        return ProteinInferenceQualityMetricStatus.WARNING
    return ProteinInferenceQualityMetricStatus.FAIL


def _validate_metric_replay(
    request: ComputeProteinInferenceQualityRequest,
    metrics: tuple[ProteinInferenceQualityMetricResult, ...],
) -> None:
    profile = _matching_profile(request)
    ledger = request.fact_ledger
    if profile is None or ledger is None:
        raise ValueError("quality metric replay requires a supported bound fact ledger")
    from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
        fact_ledger_digest,
        profile_digest,
        threshold_digest,
    )

    by_threshold = {item.metric_code: item for item in profile.thresholds}
    facts = _metric_facts(request)
    for metric in metrics:
        threshold = by_threshold[metric.metric_code]
        state, numerator, denominator, censored = facts[metric.metric_code]
        if (
            metric.observation_state is not state
            or metric.required != threshold.required
            or metric.censored_count != censored
        ):
            raise ValueError("quality metric contradicts its exact fact state or threshold")
        no_value = state in {
            ProteinInferenceQualityObservationState.MISSING,
            ProteinInferenceQualityObservationState.NOT_APPLICABLE,
            ProteinInferenceQualityObservationState.UNSUPPORTED,
        }
        if no_value:
            expected_status = (
                ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
                if state is ProteinInferenceQualityObservationState.NOT_APPLICABLE
                else ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
            )
            if metric.status is not expected_status:
                raise ValueError("quality metric status contradicts its fact state")
        elif (
            metric.numerator != numerator
            or metric.denominator != denominator
            or metric.status is not _status_for_ratio(numerator, denominator, threshold)
        ):
            raise ValueError("quality metric ratio or threshold status does not replay")
        expected_provenance = ProteinInferenceQualityMetricProvenance(
            admission_result_digest=request.raw_quality_receipt.admission_result_digest,
            fact_ledger_digest=fact_ledger_digest(ledger),
            profile_digest=profile_digest(profile),
            threshold_digest=threshold_digest(threshold),
            source_binding_digest=ledger.source_binding_digest,
            claim_binding_digest=ledger.claim_binding_digest,
        )
        if metric.provenance != expected_provenance:
            raise ValueError("quality metric provenance does not bind its exact inputs")


def finding_for(
    code: ProteinInferenceQualityFindingCode,
    metric_codes: tuple[ProteinInferenceQualityMetricCode, ...] = (),
    source_ids: tuple[Identifier, ...] = (),
    claim_ids: tuple[Identifier, ...] = (),
) -> ProteinInferenceQualityFinding:
    ordered_metrics = tuple(sorted(metric_codes))
    ordered_sources = tuple(sorted(source_ids))
    ordered_claims = tuple(sorted(claim_ids))
    digest = sha256_digest(
        {
            "code": code,
            "metric_codes": ordered_metrics,
            "source_ids": ordered_sources,
            "claim_ids": ordered_claims,
        }
    )
    suffix = digest.removeprefix("sha256:")[:16]
    return ProteinInferenceQualityFinding.model_construct(
        finding_id=f"finding.m0304.{code.value}.{suffix}",
        code=code,
        action=_ACTION_BY_FINDING_CODE[code],
        metric_codes=ordered_metrics,
        source_ids=ordered_sources,
        claim_ids=ordered_claims,
        message=_MESSAGE_BY_FINDING_CODE[code],
    )


def raw_quality_receipt(value: object) -> ProteinInferenceRawQualityReceipt:
    """Strictly project a genuine full M03-03 result without raw-byte traversal."""

    result = ProteinInferenceRawAdmissionResult.model_validate(value, strict=True)
    request = result.request
    lineage_count = len(request.lineage_receipt.artifacts)
    traversable = (
        result.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
        and lineage_count <= M0304_MAX_LINEAGE_ARTIFACTS
    )
    declarations = {item.source_id: item for item in request.sources}
    sources = (
        tuple(
            ProteinInferenceRawQualitySourceReceipt(
                source_id=item.source_id,
                role=item.role,
                bound_claim_id=declarations[item.source_id].bound_claim_id,
                artifact_digest=declarations[item.source_id].artifact.digest,
                source_digest=item.source_digest,
                source_size_bytes=item.source_size_bytes,
                decoded_digest=item.decoded_digest,
                decoded_size_bytes=item.decoded_size_bytes,
                detected_format=item.detected_format,
                detected_version=item.detected_version,
                compression=item.compression,
                record_count=item.record_count,
                reference_count=item.reference_count,
                build=item.build,
                diagnostic_codes=tuple(sorted({diag.code for diag in item.diagnostics})),
            )
            for item in sorted(result.raw_inputs, key=lambda value: value.source_id)
        )
        if traversable
        else ()
    )
    claims = (
        tuple(
            ProteinInferenceRawQualityClaimReceipt(
                claim_id=item.claim_id,
                claim_role=item.claim_role,
                artifact_digest=item.artifact.digest,
                lineage_path_digest=item.lineage_path_digest,
                evidence_state=item.evidence_state,
                finding_codes=tuple(sorted(item.finding_codes)),
            )
            for item in sorted(
                request.lineage_receipt.artifacts,
                key=lambda value: value.claim_id,
            )
        )
        if traversable
        else ()
    )
    protocol = request.protocol_receipt
    search = protocol.search_space
    payload = {
        "receipt_version": M0304_CONTRACT_VERSION,
        "admission_result_digest": result.result_digest,
        "admission_request_digest": result.request_digest,
        "admission_policy_digest": result.policy_digest,
        "admission_configuration_digest": result.configuration_digest,
        "protocol_receipt_digest": result.receipt.protocol_receipt_digest,
        "lineage_receipt_digest": result.receipt.lineage_receipt_digest,
        "source_manifest_digest": result.receipt.source_manifest_digest,
        "protocol_result_digest": protocol.protocol_result_digest,
        "protocol_digest": protocol.protocol_digest,
        "search_space_digest": protocol.search_space_digest,
        "identity_subject_digest": protocol.identity_subject_digest,
        "identity_resolution_digest": request.lineage_receipt.identity_resolution_digest,
        "lineage_result_digest": request.lineage_receipt.lineage_result_digest,
        "lineage_graph_digest": request.lineage_receipt.graph_digest,
        "upstream_disposition": result.disposition,
        "upstream_support_status": result.support.status,
        "upstream_human_review_required": result.human_review_required,
        "upstream_completed_at": result.completed_at,
        "assay_protocol_version": protocol.assay_protocol_version,
        "controlled_vocabulary_id": protocol.controlled_vocabulary_id,
        "controlled_vocabulary_version": protocol.controlled_vocabulary_version,
        "unit_system_version": protocol.unit_system_version,
        "search_space_build_id": search.build_id,
        "search_space_release": search.release,
        "target_decoy_strategy": search.target_decoy_strategy,
        "search_space_composition": search.composition,
        "source_count": len(request.sources),
        "lineage_artifact_count": lineage_count,
        "sources": sources,
        "claims": claims,
    }
    from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
        raw_quality_receipt_digest,
    )

    return ProteinInferenceRawQualityReceipt.model_validate(
        {**payload, "receipt_digest": raw_quality_receipt_digest(payload)},
        strict=True,
    )


def _ledger_bindings_close(request: ComputeProteinInferenceQualityRequest) -> bool:
    ledger = request.fact_ledger
    if ledger is None:
        return False
    receipt = request.raw_quality_receipt
    from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
        claim_binding_digest,
        source_binding_digest,
    )

    pairs = (
        (ledger.admission_result_digest, receipt.admission_result_digest),
        (ledger.protocol_result_digest, receipt.protocol_result_digest),
        (ledger.search_space_digest, receipt.search_space_digest),
        (ledger.identity_resolution_digest, receipt.identity_resolution_digest),
        (ledger.source_manifest_digest, receipt.source_manifest_digest),
        (ledger.source_binding_digest, source_binding_digest(receipt.sources)),
        (ledger.claim_binding_digest, claim_binding_digest(receipt.claims)),
    )
    return all(left == right for left, right in pairs)


def expected_disposition(  # noqa: PLR0911, PLR0912 - explicit safety precedence.
    request: ComputeProteinInferenceQualityRequest,
    metrics: tuple[ProteinInferenceQualityMetricResult, ...] = (),
    findings: tuple[ProteinInferenceQualityFinding, ...] = (),
) -> ProteinInferenceQualityDisposition:
    """Apply reject > quarantine > abstain > qualified precedence."""

    upstream = request.raw_quality_receipt.upstream_disposition
    if upstream is ProteinInferenceAdmissionDisposition.REJECTED:
        return ProteinInferenceQualityDisposition.REJECTED
    if upstream is ProteinInferenceAdmissionDisposition.QUARANTINED:
        return ProteinInferenceQualityDisposition.QUARANTINED
    if upstream is ProteinInferenceAdmissionDisposition.ABSTAINED:
        return ProteinInferenceQualityDisposition.ABSTAINED
    if request.raw_quality_receipt.lineage_artifact_count > M0304_MAX_LINEAGE_ARTIFACTS:
        return ProteinInferenceQualityDisposition.ABSTAINED
    if (
        request.raw_quality_receipt.lineage_artifact_count > request.policy.max_lineage_artifacts
        or request.raw_quality_receipt.source_count > request.policy.max_sources
    ):
        return ProteinInferenceQualityDisposition.ABSTAINED
    if not _ledger_bindings_close(request):
        return ProteinInferenceQualityDisposition.QUARANTINED
    if _matching_profile(request) is None:
        return ProteinInferenceQualityDisposition.ABSTAINED
    actions = {item.action for item in findings}
    if ProteinInferenceQualityFindingAction.REJECT in actions:
        return ProteinInferenceQualityDisposition.REJECTED
    if ProteinInferenceQualityFindingAction.QUARANTINE in actions:
        return ProteinInferenceQualityDisposition.QUARANTINED
    if ProteinInferenceQualityFindingAction.ABSTAIN in actions:
        return ProteinInferenceQualityDisposition.ABSTAINED
    if any(
        item.status
        in {
            ProteinInferenceQualityMetricStatus.WARNING,
            ProteinInferenceQualityMetricStatus.FAIL,
        }
        and item.required
        for item in metrics
    ) or any(item.status is ProteinInferenceQualityMetricStatus.FAIL for item in metrics):
        return ProteinInferenceQualityDisposition.QUARANTINED
    if any(
        item.required and item.status is ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
        for item in metrics
    ):
        return ProteinInferenceQualityDisposition.ABSTAINED
    profile = _matching_profile(request)
    if any(
        item.required
        and item.status is ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
        and not (
            item.metric_code is ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY
            and profile is not None
            and not profile.controls_applicable
        )
        for item in metrics
    ):
        return ProteinInferenceQualityDisposition.ABSTAINED
    return ProteinInferenceQualityDisposition.QUALIFIED


def expected_quality_findings(  # noqa: PLR0911, PLR0912 - closed finding matrix.
    request: ComputeProteinInferenceQualityRequest,
    metrics: tuple[ProteinInferenceQualityMetricResult, ...] = (),
) -> tuple[ProteinInferenceQualityFinding, ...]:
    """Derive the exact closed finding set from one request and metric collection."""

    upstream = request.raw_quality_receipt.upstream_disposition
    if upstream is ProteinInferenceAdmissionDisposition.REJECTED:
        return (finding_for(ProteinInferenceQualityFindingCode.UPSTREAM_REJECTED),)
    if upstream is ProteinInferenceAdmissionDisposition.QUARANTINED:
        return (finding_for(ProteinInferenceQualityFindingCode.UPSTREAM_QUARANTINED),)
    if upstream is ProteinInferenceAdmissionDisposition.ABSTAINED:
        return (finding_for(ProteinInferenceQualityFindingCode.UPSTREAM_ABSTAINED),)
    receipt = request.raw_quality_receipt
    if (
        receipt.lineage_artifact_count > request.policy.max_lineage_artifacts
        or receipt.source_count > request.policy.max_sources
    ):
        return (finding_for(ProteinInferenceQualityFindingCode.UPSTREAM_SHAPE_UNSUPPORTED),)
    if not _ledger_bindings_close(request):
        return (finding_for(ProteinInferenceQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH),)
    profile = _matching_profile(request)
    if profile is None:
        return (finding_for(ProteinInferenceQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED),)
    findings: list[ProteinInferenceQualityFinding] = []
    ledger = request.fact_ledger
    if ledger is not None:
        control_consistent = (
            profile.controls_applicable
            and ledger.states.control_recovery
            is not ProteinInferenceQualityObservationState.NOT_APPLICABLE
        ) or (
            not profile.controls_applicable
            and ledger.states.control_recovery
            is ProteinInferenceQualityObservationState.NOT_APPLICABLE
            and ledger.counts.control_expected_group_count == 0
            and ledger.counts.control_recovered_group_count == 0
        )
        if not control_consistent:
            findings.append(
                finding_for(
                    ProteinInferenceQualityFindingCode.CROSS_METRIC_INCONSISTENCY,
                    metric_codes=(ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY,),
                )
            )
    for metric in metrics:
        codes = (metric.metric_code,)
        if metric.required and (
            metric.observation_state is ProteinInferenceQualityObservationState.MISSING
        ):
            code = ProteinInferenceQualityFindingCode.REQUIRED_METRIC_MISSING
        elif metric.required and (
            metric.observation_state is ProteinInferenceQualityObservationState.UNSUPPORTED
        ):
            code = ProteinInferenceQualityFindingCode.REQUIRED_METRIC_UNSUPPORTED
        elif metric.required and (
            metric.status is ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
            or (
                metric.status is ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
                and not (
                    metric.metric_code is ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY
                    and not profile.controls_applicable
                )
            )
        ):
            if (
                metric.metric_code is ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY
                and metric.status is ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
                and profile.controls_applicable
            ):
                continue
            code = ProteinInferenceQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE
        elif metric.required and metric.status is ProteinInferenceQualityMetricStatus.WARNING:
            code = ProteinInferenceQualityFindingCode.REQUIRED_METRIC_WARNING
        elif metric.status is ProteinInferenceQualityMetricStatus.FAIL:
            code = ProteinInferenceQualityFindingCode.METRIC_THRESHOLD_FAILED
        elif not metric.required and metric.status is ProteinInferenceQualityMetricStatus.WARNING:
            code = ProteinInferenceQualityFindingCode.OPTIONAL_METRIC_WARNING
        else:
            continue
        findings.append(finding_for(code, metric_codes=codes))
    return tuple(sorted(findings, key=canonical_json_bytes))


def expected_computation_receipt(
    request: ComputeProteinInferenceQualityRequest,
    disposition: ProteinInferenceQualityDisposition,
    profile: ProteinInferenceAssayQualityProfile | None = None,
) -> ProteinInferenceQualityComputationReceipt:
    from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
        configuration_digest,
        fact_ledger_digest,
        policy_digest,
        profile_digest,
        raw_quality_receipt_digest,
    )

    active = profile if profile is not None else _matching_profile(request)
    return ProteinInferenceQualityComputationReceipt(
        raw_quality_receipt_digest=raw_quality_receipt_digest(request.raw_quality_receipt),
        fact_ledger_digest=(
            fact_ledger_digest(request.fact_ledger) if request.fact_ledger is not None else None
        ),
        policy_digest=policy_digest(request.policy),
        configuration_digest=configuration_digest(request.policy),
        profile_digest=profile_digest(active) if active is not None else None,
        disposition=disposition,
    )


def expected_support(
    disposition: ProteinInferenceQualityDisposition,
    metrics: tuple[ProteinInferenceQualityMetricResult, ...] = (),
) -> SupportDecision:
    optional_warning = any(
        item.status is ProteinInferenceQualityMetricStatus.WARNING and not item.required
        for item in metrics
    )
    if disposition is ProteinInferenceQualityDisposition.QUALIFIED:
        if optional_warning:
            return SupportDecision(
                status=SupportStatus.LIMITED,
                reason_code="protein_inference_quality_qualified_with_optional_warning",
                rationale=(
                    "All required quality metrics passed; an optional warning limits support."
                ),
            )
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="protein_inference_quality_qualified",
            rationale="All required protein-inference quality metrics passed.",
        )
    if disposition is ProteinInferenceQualityDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="protein_inference_quality_quarantined",
            rationale="A binding contradiction or threshold outcome requires review.",
        )
    reason = (
        "protein_inference_quality_rejected"
        if disposition is ProteinInferenceQualityDisposition.REJECTED
        else "protein_inference_quality_abstained"
    )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code=reason,
        rationale="The upstream state or quality profile is outside the reviewed domain.",
    )


def expected_uncertainty(
    disposition: ProteinInferenceQualityDisposition,
) -> UncertaintyProfile:
    del disposition
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0304_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=M0304_SENSITIVITY_NOTES,
    )


def expected_control_decisions(
    request: ComputeProteinInferenceQualityRequest,
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


def quality_evidence_index(
    request: ComputeProteinInferenceQualityRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    active_profile = _matching_profile(request)
    artifacts = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
        *((active_profile.evidence,) if active_profile is not None else ()),
        *((item.evidence for item in active_profile.thresholds) if active_profile else ()),
        *((request.fact_ledger.evidence,) if request.fact_ledger is not None else ()),
    )
    unique = {
        (item.artifact_id, item.version, item.digest, item.media_type): item for item in artifacts
    }
    return tuple(
        EvidenceReference(
            reference=unique[key],
            role="evidence",
            claim=M0304_EVIDENCE_CLAIM,
        )
        for key in sorted(unique, key=canonical_json_bytes)
    )


def expected_provenance(
    request: ComputeProteinInferenceQualityRequest,
    disposition: ProteinInferenceQualityDisposition,
) -> ProvenanceRecord:
    del disposition
    from glio_proteogen.contracts.m03_04.canonical import (  # noqa: PLC0415
        canonical_request_digest,
        configuration_digest,
        fact_ledger_digest,
        policy_digest,
        profile_digest,
        raw_quality_receipt_digest,
    )

    request_hash = canonical_request_digest(request)
    policy_hash = policy_digest(request.policy)
    config_hash = configuration_digest(request.policy)
    controls = expected_control_decisions(request)
    evidence = quality_evidence_index(request)
    profile = _matching_profile(request)
    input_digests = tuple(
        sorted(
            {
                request_hash,
                policy_hash,
                config_hash,
                raw_quality_receipt_digest(request.raw_quality_receipt),
                request.raw_quality_receipt.admission_result_digest,
                request.raw_quality_receipt.protocol_result_digest,
                request.raw_quality_receipt.search_space_digest,
                request.raw_quality_receipt.identity_resolution_digest,
                request.raw_quality_receipt.source_manifest_digest,
                *(
                    (fact_ledger_digest(request.fact_ledger),)
                    if request.fact_ledger is not None
                    else ()
                ),
                *((profile_digest(profile),) if profile is not None else ()),
                *(item.reference.digest for item in evidence),
                *(item.evidence_digest for item in controls),
            }
        )
    )
    context = request.context
    refs = context.references
    suffix = request_hash.removeprefix("sha256:")
    return ProvenanceRecord(
        activity_id=f"activity.m0304.{suffix}",
        actor_id=context.actor_id,
        module_id=M0304_MODULE_ID,
        module_version=M0304_CONTRACT_VERSION,
        generated_at=context.occurred_at,
        input_digests=input_digests,
        configuration_digest=config_hash,
        consent_decision_id=refs.consent.decision_id,
        consent_state=ConsentState.GRANTED,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code=M0304_QUALITY_LIMITATION_CODE,
            statement=(
                "This result evaluates protein-inference evidence-graph quality only; it does "
                "not infer a protein, proteoform, complex, pathway, biological activity, "
                "clinical state, or absence."
            ),
        ),
        Limitation(
            code=M0304_AUTHORITY_LIMITATION_CODE,
            statement=(
                "Content digests prove deterministic self-consistency of caller-declared "
                "metadata, facts, and controls, not issuer authenticity, raw-byte parser "
                "execution, external reference truth, or clinical readiness."
            ),
        ),
    )


# Root-level naming aliases retained for the module-plan vocabulary.
ComputeProteinInferenceEvidenceGraphQualityRequest = ComputeProteinInferenceQualityRequest
ProteinInferenceEvidenceGraphQualityProfile = ProteinInferenceQualityResult
ProteinInferenceEvidenceGraphQualityPolicy = ProteinInferenceQualityPolicy
ProteinInferenceEvidenceGraphMetricCode = ProteinInferenceQualityMetricCode


__all__ = [name for name in globals() if not name.startswith("_")]
