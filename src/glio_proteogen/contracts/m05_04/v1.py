"""Strict M05-04 fixed-point ptm_localization quality contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, cast
from weakref import WeakKeyDictionary

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    TypeAdapter,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from glio_proteogen.contracts.m05_01 import (
    PtmLocalizationAssayKind,
    PtmLocalizationSupportDomain,
)
from glio_proteogen.contracts.m05_03 import (
    PtmLocalizationRawInputDisposition,
    PtmLocalizationRawInputRole,
    PtmLocalizationRawInputValidationResult,
    opaque_ptm_localization_raw_input_identifier,
)
from glio_proteogen.contracts.m05_03 import (
    normalized_result as normalized_m0503_result,
)
from glio_proteogen.contracts.m05_04.canonical import (
    assay_quality_digest,
    canonical_request_digest,
    configuration_digest,
    fact_ledger_digest,
    metric_digest,
    normalized_request,
    policy_digest,
    profile_digest,
    receipt_digest,
    result_payload_digest,
    role_facts_digest,
    threshold_digest,
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

M0504_MODULE_ID: Final = "GLIO-PROTEOGEN-M05-04"
M0504_OPERATION: Final = "compute_ptm_localization_quality_metrics"
M0504_CONTRACT_VERSION: Final = "1.0.0"
M0504_PARENT: Final = "variant_peptide"
M0504_OWNER: Final = "Platform engineering"
M0504_SAFETY_CLASS: Final = "S2"
M0504_GATE: Final = "G1"
M0504_ROLE_COUNT: Final = 4
M0504_METRIC_COUNT: Final = 8
M0504_COMPUTED_METRIC_COUNT: Final = 32
M0504_RATE_SCALE: Final = 1_000_000
M0504_MAX_COUNT: Final = 9_223_372_036_854_775_807
M0504_MIN_PROFILES: Final = 4
M0504_MAX_PROFILES: Final = 32
M0504_MAX_APPROVED_VERSIONS: Final = 32
M0504_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0504_MAX_FINDINGS: Final = 48
M0504_MIN_EVIDENCE: Final = 12
M0504_MAX_EVIDENCE: Final = 45
M0504_LIMITATION_COUNT: Final = 3
_M0504_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0504_EVIDENCE_CLAIM: Final = "Caller-declared content-addressed M05-04 aggregate quality evidence."

_VALIDATION_CAPABILITY_SEAL: Final = object()
_RAW_CAPABILITY_CONTEXT_KEY: Final = "_m0504_raw_input_replay_capability"
_REQUEST_CAPABILITY_CONTEXT_KEY: Final = "_m0504_validated_request_capability"


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _RawInputReplayCapability:
    seal: object
    source_bytes: bytes
    normalized_bytes: bytes
    result: PtmLocalizationRawInputValidationResult


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _ValidatedRequestCapability:
    seal: object
    request: ComputePtmLocalizationQualityMetricsRequest
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest


_ISSUED_RAW_CAPABILITIES: Final[
    WeakKeyDictionary[
        _RawInputReplayCapability,
        tuple[bytes, bytes, PtmLocalizationRawInputValidationResult],
    ]
] = WeakKeyDictionary()
_ISSUED_REQUEST_CAPABILITIES: Final[
    WeakKeyDictionary[
        _ValidatedRequestCapability,
        tuple[
            ComputePtmLocalizationQualityMetricsRequest,
            Sha256Digest,
            Sha256Digest,
            Sha256Digest,
        ],
    ]
] = WeakKeyDictionary()


def _raw_capability_is_issued(capability: _RawInputReplayCapability) -> bool:
    snapshot = _ISSUED_RAW_CAPABILITIES.get(capability)
    return (
        snapshot is not None
        and snapshot[0] == capability.source_bytes
        and snapshot[1] == capability.normalized_bytes
        and snapshot[2] is capability.result
    )


def _request_capability_is_issued(capability: _ValidatedRequestCapability) -> bool:
    snapshot = _ISSUED_REQUEST_CAPABILITIES.get(capability)
    return (
        snapshot is not None
        and snapshot[0] is capability.request
        and snapshot[1] == capability.request_digest
        and snapshot[2] == capability.policy_digest
        and snapshot[3] == capability.configuration_digest
    )


_OPAQUE_IDENTIFIER = re.compile(
    r"^(?:request|actor|decision|policy|profile|ledger|fact|evidence|reviewer)"
    r"\.[0-9a-f]{64}$"
)
type PtmLocalizationQualityOpaqueNamespace = Literal[
    "request", "actor", "decision", "policy", "profile", "ledger", "fact", "evidence", "reviewer"
]


def opaque_ptm_localization_quality_identifier(
    namespace: PtmLocalizationQualityOpaqueNamespace, value: Identifier
) -> Identifier:
    """Validate an M05-04 caller-reflected opaque identifier."""

    if _OPAQUE_IDENTIFIER.fullmatch(value) is None or not value.startswith(f"{namespace}."):
        raise ValueError("M05-04 identifiers must use their exact opaque local namespace")
    return value


class PtmLocalizationQualityMetricCode(StrEnum):
    RAW_INPUT_COMPLETENESS = "raw_input_completeness"
    VALID_RECORD_COVERAGE = "valid_record_coverage"
    ASSAY_FEATURE_COVERAGE = "assay_feature_coverage"
    REFERENCE_MAPPING_COVERAGE = "reference_mapping_coverage"
    DETECTION_LIMIT_BURDEN = "detection_limit_burden"
    CONTROL_MATERIAL_RECOVERY = "control_material_recovery"
    SAMPLE_CONTEXT_BINDING_COHERENCE = "sample_context_binding_coherence"
    CROSS_INPUT_CONSISTENCY = "cross_input_consistency"


class PtmLocalizationQualityObservationState(StrEnum):
    OBSERVED = "observed"
    CENSORED = "censored"
    MISSING = "missing"
    INDETERMINATE = "indeterminate"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"


class PtmLocalizationQualityMetricStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - domain status.
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"
    NOT_APPLICABLE = "not_applicable"


class PtmLocalizationQualityMetricDirection(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"


class PtmLocalizationQualityDisposition(StrEnum):
    QUALIFIED = "qualified"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class PtmLocalizationQualityFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


class PtmLocalizationQualityFindingCode(StrEnum):
    UPSTREAM_RAW_INPUTS_QUARANTINED = "upstream_raw_inputs_quarantined"
    UPSTREAM_RAW_INPUTS_ABSTAINED = "upstream_raw_inputs_abstained"
    FACT_LEDGER_BINDING_MISMATCH = "fact_ledger_binding_mismatch"
    ASSAY_PROFILE_UNSUPPORTED = "assay_profile_unsupported"
    ASSAY_PROTOCOL_VERSION_MISMATCH = "assay_protocol_version_mismatch"
    SPECIMEN_PROCESSING_VERSION_MISMATCH = "specimen_processing_version_mismatch"
    UNIT_SYSTEM_VERSION_MISMATCH = "unit_system_version_mismatch"
    REQUIRED_METRIC_MISSING = "required_metric_missing"
    REQUIRED_METRIC_UNSUPPORTED = "required_metric_unsupported"
    REQUIRED_METRIC_NOT_EVALUABLE = "required_metric_not_evaluable"
    REQUIRED_METRIC_WARNING = "required_metric_warning"
    METRIC_THRESHOLD_FAILED = "metric_threshold_failed"
    OPTIONAL_METRIC_WARNING = "optional_metric_warning"
    CROSS_METRIC_INCONSISTENCY = "cross_metric_inconsistency"


_DIRECTION_BY_METRIC: Final = dict.fromkeys(
    PtmLocalizationQualityMetricCode, PtmLocalizationQualityMetricDirection.AT_LEAST
)
_DIRECTION_BY_METRIC[PtmLocalizationQualityMetricCode.DETECTION_LIMIT_BURDEN] = (
    PtmLocalizationQualityMetricDirection.AT_MOST
)
_ACTION_BY_FINDING: Final = {
    PtmLocalizationQualityFindingCode.UPSTREAM_RAW_INPUTS_QUARANTINED: (
        PtmLocalizationQualityFindingAction.QUARANTINE
    ),
    PtmLocalizationQualityFindingCode.UPSTREAM_RAW_INPUTS_ABSTAINED: (
        PtmLocalizationQualityFindingAction.ABSTAIN
    ),
    PtmLocalizationQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH: (
        PtmLocalizationQualityFindingAction.QUARANTINE
    ),
    PtmLocalizationQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED: (
        PtmLocalizationQualityFindingAction.ABSTAIN
    ),
    PtmLocalizationQualityFindingCode.ASSAY_PROTOCOL_VERSION_MISMATCH: (
        PtmLocalizationQualityFindingAction.QUARANTINE
    ),
    PtmLocalizationQualityFindingCode.SPECIMEN_PROCESSING_VERSION_MISMATCH: (
        PtmLocalizationQualityFindingAction.QUARANTINE
    ),
    PtmLocalizationQualityFindingCode.UNIT_SYSTEM_VERSION_MISMATCH: (
        PtmLocalizationQualityFindingAction.QUARANTINE
    ),
    PtmLocalizationQualityFindingCode.REQUIRED_METRIC_MISSING: (
        PtmLocalizationQualityFindingAction.ABSTAIN
    ),
    PtmLocalizationQualityFindingCode.REQUIRED_METRIC_UNSUPPORTED: (
        PtmLocalizationQualityFindingAction.ABSTAIN
    ),
    PtmLocalizationQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE: (
        PtmLocalizationQualityFindingAction.ABSTAIN
    ),
    PtmLocalizationQualityFindingCode.REQUIRED_METRIC_WARNING: (
        PtmLocalizationQualityFindingAction.QUARANTINE
    ),
    PtmLocalizationQualityFindingCode.METRIC_THRESHOLD_FAILED: (
        PtmLocalizationQualityFindingAction.QUARANTINE
    ),
    PtmLocalizationQualityFindingCode.OPTIONAL_METRIC_WARNING: (
        PtmLocalizationQualityFindingAction.RECORD
    ),
    PtmLocalizationQualityFindingCode.CROSS_METRIC_INCONSISTENCY: (
        PtmLocalizationQualityFindingAction.QUARANTINE
    ),
}
_MESSAGE_BY_FINDING: Final = {
    code: code.value.replace("_", " ").capitalize() + "."
    for code in PtmLocalizationQualityFindingCode
}
_CONTROL_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.control+json"
_POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-04.policy+json"
_PROFILE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-04.assay-profile+json"
_LEDGER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-04.fact-ledger+json"
_FACT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-04.role-fact+json"


def _owned_artifact(value: ArtifactReference, media_type: str) -> ArtifactReference:
    opaque_ptm_localization_quality_identifier("evidence", value.artifact_id)
    if value.media_type != media_type:
        raise ValueError("M05-04 artifact media type is not owned by this contract region")
    return value


def _require_consistent_evidence_identities(
    artifacts: tuple[ArtifactReference, ...],
) -> None:
    seen: dict[tuple[Identifier, SemanticVersion], tuple[Sha256Digest, str]] = {}
    for artifact in artifacts:
        identity = (artifact.artifact_id, artifact.version)
        content = (artifact.digest, artifact.media_type)
        previous = seen.setdefault(identity, content)
        if previous != content:
            raise ValueError("one M05-04 evidence identity cannot declare conflicting content")


class PtmLocalizationQualityThreshold(FrozenModel):
    metric_code: PtmLocalizationQualityMetricCode
    direction: PtmLocalizationQualityMetricDirection
    pass_threshold_ppm: int = Field(ge=0, le=M0504_RATE_SCALE)
    warning_threshold_ppm: int = Field(ge=0, le=M0504_RATE_SCALE)
    required: bool

    @model_validator(mode="after")
    def thresholds_are_directionally_closed(self) -> PtmLocalizationQualityThreshold:
        if self.direction is not _DIRECTION_BY_METRIC[self.metric_code]:
            raise ValueError("quality threshold direction contradicts its metric")
        if self.direction is PtmLocalizationQualityMetricDirection.AT_LEAST:
            if self.warning_threshold_ppm > self.pass_threshold_ppm:
                raise ValueError("at-least warning threshold cannot exceed pass threshold")
        elif self.warning_threshold_ppm < self.pass_threshold_ppm:
            raise ValueError("at-most warning threshold cannot be below pass threshold")
        return self


class PtmLocalizationAssayQualityProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    role: PtmLocalizationRawInputRole
    assay_kind: PtmLocalizationAssayKind | None = None
    support_domain: PtmLocalizationSupportDomain | None = None
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0504_MAX_APPROVED_VERSIONS
    )
    approved_specimen_processing_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0504_MAX_APPROVED_VERSIONS
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0504_MAX_APPROVED_VERSIONS
    )
    controls_applicable: bool
    thresholds: tuple[PtmLocalizationQualityThreshold, ...] = Field(
        min_length=M0504_METRIC_COUNT, max_length=M0504_METRIC_COUNT
    )
    evidence: ArtifactReference

    @field_validator(
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_unit_system_versions",
    )
    @classmethod
    def approved_versions_are_canonical(
        cls, values: tuple[SemanticVersion, ...]
    ) -> tuple[SemanticVersion, ...]:
        if len(values) != len(set(values)):
            raise ValueError("approved versions must be unique")
        return tuple(sorted(values))

    @field_validator("thresholds")
    @classmethod
    def thresholds_are_canonical(
        cls, values: tuple[PtmLocalizationQualityThreshold, ...]
    ) -> tuple[PtmLocalizationQualityThreshold, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(value, _PROFILE_MEDIA_TYPE)

    @model_validator(mode="after")
    def profile_is_closed(self) -> PtmLocalizationAssayQualityProfile:
        opaque_ptm_localization_quality_identifier("profile", self.profile_id)
        proteome_role = self.role is PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME
        if proteome_role != (self.assay_kind is not None and self.support_domain is not None):
            raise ValueError(
                "assay kind and support domain are required only for the proteome role"
            )
        if not proteome_role and (self.assay_kind is not None or self.support_domain is not None):
            raise ValueError("non-proteome profiles cannot declare mass-spectrometry axes")
        if (
            proteome_role
            and self.support_domain is not PtmLocalizationSupportDomain.REVIEWED_SUPPORTED
        ):
            raise ValueError("quality profiles cannot approve novel or unresolved assay support")
        codes = tuple(item.metric_code for item in self.thresholds)
        if len(codes) != len(set(codes)) or set(codes) != set(PtmLocalizationQualityMetricCode):
            raise ValueError("quality profile requires every metric exactly once")
        return self


class PtmLocalizationQualityPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_count: int = Field(gt=0, le=M0504_MAX_COUNT)
    profiles: tuple[PtmLocalizationAssayQualityProfile, ...] = Field(
        min_length=M0504_MIN_PROFILES, max_length=M0504_MAX_PROFILES
    )
    quarantine_required_warnings: Literal[True] = True
    abstain_required_not_evaluable: Literal[True] = True
    retain_censored_detection: Literal[True] = True
    never_infer_negative_from_missing: Literal[True] = True
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("profiles")
    @classmethod
    def profiles_are_canonical(
        cls, values: tuple[PtmLocalizationAssayQualityProfile, ...]
    ) -> tuple[PtmLocalizationAssayQualityProfile, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(value, _POLICY_MEDIA_TYPE)

    @model_validator(mode="after")
    def profiles_are_total_and_disjoint(self) -> PtmLocalizationQualityPolicy:
        opaque_ptm_localization_quality_identifier("policy", self.policy_id)
        opaque_ptm_localization_quality_identifier("reviewer", self.reviewed_by)
        identities = tuple((item.profile_id, item.version) for item in self.profiles)
        if len(identities) != len(set(identities)):
            raise ValueError("quality profile identities must be unique")
        if {item.role for item in self.profiles} != set(PtmLocalizationRawInputRole):
            raise ValueError("quality policy must cover all four roles")
        _require_consistent_evidence_identities(
            (self.evidence, *(item.evidence for item in self.profiles))
        )
        for index, left in enumerate(self.profiles):
            for right in self.profiles[index + 1 :]:
                overlap = (
                    left.role is right.role
                    and left.assay_kind is right.assay_kind
                    and left.support_domain is right.support_domain
                    and left.controls_applicable is right.controls_applicable
                    and bool(
                        set(left.approved_assay_protocol_versions)
                        & set(right.approved_assay_protocol_versions)
                    )
                    and bool(
                        set(left.approved_specimen_processing_versions)
                        & set(right.approved_specimen_processing_versions)
                    )
                    and bool(
                        set(left.approved_unit_system_versions)
                        & set(right.approved_unit_system_versions)
                    )
                )
                if overlap:
                    raise ValueError("quality profile match domains must be disjoint")
        return self


class PtmLocalizationQualityRoleCounts(FrozenModel):
    declared_record_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    parsed_record_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    valid_record_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    expected_feature_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    observed_feature_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    reference_eligible_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    reference_mapped_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    detection_eligible_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    above_detection_limit_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    below_detection_limit_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    control_expected_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    control_recovered_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    context_applicable_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    context_coherent_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    cross_input_applicable_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    cross_input_coherent_count: int = Field(ge=0, le=M0504_MAX_COUNT)

    @model_validator(mode="after")
    def count_partitions_close(self) -> PtmLocalizationQualityRoleCounts:
        if not (
            self.valid_record_count <= self.parsed_record_count <= self.declared_record_count
            and self.observed_feature_count <= self.expected_feature_count
            and self.reference_mapped_count <= self.reference_eligible_count
            and self.control_recovered_count <= self.control_expected_count
            and self.context_coherent_count <= self.context_applicable_count
            and self.cross_input_coherent_count <= self.cross_input_applicable_count
        ):
            raise ValueError("quality count numerator cannot exceed its denominator")
        if (
            self.above_detection_limit_count + self.below_detection_limit_count
            != self.detection_eligible_count
        ):
            raise ValueError("detection counts must exactly partition eligible records")
        return self


class PtmLocalizationQualityRoleFactStates(FrozenModel):
    raw_input_completeness: PtmLocalizationQualityObservationState
    valid_record_coverage: PtmLocalizationQualityObservationState
    assay_feature_coverage: PtmLocalizationQualityObservationState
    reference_mapping_coverage: PtmLocalizationQualityObservationState
    detection_limit_burden: PtmLocalizationQualityObservationState
    control_material_recovery: PtmLocalizationQualityObservationState
    sample_context_binding_coherence: PtmLocalizationQualityObservationState
    cross_input_consistency: PtmLocalizationQualityObservationState


_COUNT_FIELDS_BY_METRIC: Final = {
    PtmLocalizationQualityMetricCode.RAW_INPUT_COMPLETENESS: (
        "parsed_record_count",
        "declared_record_count",
    ),
    PtmLocalizationQualityMetricCode.VALID_RECORD_COVERAGE: (
        "valid_record_count",
        "parsed_record_count",
    ),
    PtmLocalizationQualityMetricCode.ASSAY_FEATURE_COVERAGE: (
        "observed_feature_count",
        "expected_feature_count",
    ),
    PtmLocalizationQualityMetricCode.REFERENCE_MAPPING_COVERAGE: (
        "reference_mapped_count",
        "reference_eligible_count",
    ),
    PtmLocalizationQualityMetricCode.DETECTION_LIMIT_BURDEN: (
        "below_detection_limit_count",
        "detection_eligible_count",
    ),
    PtmLocalizationQualityMetricCode.CONTROL_MATERIAL_RECOVERY: (
        "control_recovered_count",
        "control_expected_count",
    ),
    PtmLocalizationQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE: (
        "context_coherent_count",
        "context_applicable_count",
    ),
    PtmLocalizationQualityMetricCode.CROSS_INPUT_CONSISTENCY: (
        "cross_input_coherent_count",
        "cross_input_applicable_count",
    ),
}


class PtmLocalizationQualityRoleFacts(FrozenModel):
    fact_id: Identifier
    role: PtmLocalizationRawInputRole
    input_id: Identifier
    validated_input_digest: Sha256Digest
    document_digest: Sha256Digest
    counts: PtmLocalizationQualityRoleCounts
    states: PtmLocalizationQualityRoleFactStates
    evidence: ArtifactReference

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(value, _FACT_MEDIA_TYPE)

    @model_validator(mode="after")
    def fact_shape_is_closed(self) -> PtmLocalizationQualityRoleFacts:
        opaque_ptm_localization_quality_identifier("fact", self.fact_id)
        opaque_ptm_localization_raw_input_identifier("input", self.input_id)
        states = {
            code: cast("PtmLocalizationQualityObservationState", getattr(self.states, code.value))
            for code in PtmLocalizationQualityMetricCode
        }
        for code, state in states.items():
            if state is PtmLocalizationQualityObservationState.CENSORED and (
                code is not PtmLocalizationQualityMetricCode.DETECTION_LIMIT_BURDEN
            ):
                raise ValueError("only detection-limit burden may be censored")
            numerator_field, denominator_field = _COUNT_FIELDS_BY_METRIC[code]
            if state not in {
                PtmLocalizationQualityObservationState.OBSERVED,
                PtmLocalizationQualityObservationState.CENSORED,
            } and (
                getattr(self.counts, numerator_field) != 0
                or getattr(self.counts, denominator_field) != 0
            ):
                raise ValueError("non-observed quality facts must carry zero count partitions")
        detection_censored = (
            states[PtmLocalizationQualityMetricCode.DETECTION_LIMIT_BURDEN]
            is PtmLocalizationQualityObservationState.CENSORED
        )
        if detection_censored != (self.counts.below_detection_limit_count > 0):
            raise ValueError("detection censoring must exactly retain positive below-limit count")
        return self


class PtmLocalizationQualityFactLedger(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    raw_input_result_digest: Sha256Digest
    raw_input_receipt_digest: Sha256Digest
    role_facts: tuple[PtmLocalizationQualityRoleFacts, ...] = Field(
        min_length=M0504_ROLE_COUNT, max_length=M0504_ROLE_COUNT
    )
    evidence: ArtifactReference
    recorded_at: AwareDatetime
    ledger_digest: Sha256Digest

    @field_validator("role_facts")
    @classmethod
    def role_facts_are_canonical(
        cls, values: tuple[PtmLocalizationQualityRoleFacts, ...]
    ) -> tuple[PtmLocalizationQualityRoleFacts, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("evidence")
    @classmethod
    def evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_artifact(value, _LEDGER_MEDIA_TYPE)

    @model_validator(mode="after")
    def ledger_is_closed(self) -> PtmLocalizationQualityFactLedger:
        opaque_ptm_localization_quality_identifier("ledger", self.ledger_id)
        roles = tuple(item.role for item in self.role_facts)
        if len(roles) != len(set(roles)) or set(roles) != set(PtmLocalizationRawInputRole):
            raise ValueError("fact ledger requires every role exactly once")
        _require_consistent_evidence_identities(
            (self.evidence, *(item.evidence for item in self.role_facts))
        )
        if self.ledger_digest == _M0504_ZERO_DIGEST:
            raise ValueError("fact-ledger digest must be final")
        if self.ledger_digest != fact_ledger_digest(self):
            raise ValueError("fact-ledger digest does not match its canonical payload")
        return self


class ComputePtmLocalizationQualityMetricsRequest(FrozenModel):
    operation: Literal["compute_ptm_localization_quality_metrics"] = M0504_OPERATION
    contract_version: Literal["1.0.0"] = M0504_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    raw_input_result: PtmLocalizationRawInputValidationResult
    policy: PtmLocalizationQualityPolicy
    fact_ledger: PtmLocalizationQualityFactLedger | None = None
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("raw_input_result", mode="wrap")
    @classmethod
    def raw_input_result_is_fully_replayed(
        cls,
        value: object,
        handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> PtmLocalizationRawInputValidationResult:
        capability = (
            info.context.get(_RAW_CAPABILITY_CONTEXT_KEY)
            if isinstance(info.context, dict)
            else None
        )
        if (
            isinstance(capability, _RawInputReplayCapability)
            and capability.seal is _VALIDATION_CAPABILITY_SEAL
            and _raw_capability_is_issued(capability)
            and _raw_input_semantic_bytes(value)
            in {capability.source_bytes, capability.normalized_bytes}
        ):
            return capability.result
        result_digest: object
        receipt_digest_value: object
        if type(value) is PtmLocalizationRawInputValidationResult:
            result_digest = value.result_digest
            receipt_digest_value = value.receipt.receipt_digest
        elif dict in type.__getattribute__(type(value), "__mro__"):
            mapping = cast("dict[object, object]", value)
            result_digest = dict.get(mapping, "result_digest")
            receipt = dict.get(mapping, "receipt")
            receipt_digest_value = (
                dict.get(receipt, "receipt_digest") if isinstance(receipt, dict) else None
            )
        else:
            return cast("PtmLocalizationRawInputValidationResult", handler(value))
        if _M0504_ZERO_DIGEST in (result_digest, receipt_digest_value):
            raise ValueError("embedded M05-03 derived digests must be final")
        parsed = (
            value
            if type(value) is PtmLocalizationRawInputValidationResult
            else PtmLocalizationRawInputValidationResult.model_validate_json(
                _raw_input_semantic_bytes(value), strict=True
            )
        )
        return PtmLocalizationRawInputValidationResult.model_validate_json(
            canonical_json_bytes(normalized_m0503_result(parsed)), strict=True
        )

    @model_validator(mode="after")
    def request_is_closed(self) -> ComputePtmLocalizationQualityMetricsRequest:
        opaque_ptm_localization_quality_identifier("request", self.request_id)
        opaque_ptm_localization_quality_identifier("request", self.context.request_id)
        opaque_ptm_localization_quality_identifier("actor", self.context.actor_id)
        if self.request_id != self.context.request_id:
            raise ValueError("request identifier must equal authorized context identifier")
        upstream = self.raw_input_result
        if upstream.disposition is PtmLocalizationRawInputDisposition.VALIDATED:
            if self.fact_ledger is None:
                raise ValueError("validated M05-03 input requires a fact ledger")
        elif self.fact_ledger is not None:
            raise ValueError("nonvalidated M05-03 input prohibits fact-ledger traversal")
        if self.policy.reviewed_at > self.context.occurred_at:
            raise ValueError("quality policy cannot postdate computation")
        if upstream.completed_at > self.context.occurred_at:
            raise ValueError("M05-03 result cannot postdate quality computation")
        if self.fact_ledger is not None and not (
            upstream.completed_at <= self.fact_ledger.recorded_at <= self.context.occurred_at
        ):
            raise ValueError("fact ledger chronology must follow M05-03 and precede computation")
        if self.fact_ledger is not None and any(
            count > self.policy.max_count
            for fact in self.fact_ledger.role_facts
            for count in fact.counts.model_dump(mode="python").values()
        ):
            raise ValueError("fact-ledger count exceeds the reviewed policy maximum")
        refs = self.context.references
        generic = (
            refs.approved_configuration,
            refs.provenance,
            refs.quality,
            refs.support,
            refs.intended_use,
        )
        if (
            refs.consent.state is not ConsentState.GRANTED
            or refs.identity_lineage.state.value != "resolved"
            or any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic)
        ):
            raise ValueError("ptm_localization quality computation is not authorized")
        if (
            refs.identity_lineage.binding_digest != upstream.receipt.identity_resolution_digest
            or refs.quality.evidence.digest != upstream.result_digest
            or refs.support.evidence.digest != upstream.receipt.receipt_digest
            or refs.intended_use.evidence.digest != upstream.receipt.intended_use_evidence_digest
            or refs.approved_configuration.evidence.digest != configuration_digest(self.policy)
        ):
            raise ValueError("M05-04 context does not bind the exact upstream result and policy")
        controls = (
            refs.approved_configuration,
            refs.identity_lineage,
            refs.provenance,
            refs.consent,
            refs.quality,
            refs.support,
            refs.intended_use,
        )
        for control in controls:
            opaque_ptm_localization_quality_identifier("decision", control.decision_id)
            _owned_artifact(control.evidence, _CONTROL_MEDIA_TYPE)
        quality_evidence_index(self)
        if len(canonical_json_bytes(normalized_request(self))) > M0504_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M05-04 request exceeds the 4 MiB ingress bound")
        return self


class PtmLocalizationQualityMetricProvenance(FrozenModel):
    raw_input_result_digest: Sha256Digest
    raw_input_receipt_digest: Sha256Digest
    fact_ledger_digest: Sha256Digest
    role_fact_digest: Sha256Digest
    profile_digest: Sha256Digest
    threshold_digest: Sha256Digest
    validated_input_digest: Sha256Digest
    document_digest: Sha256Digest


class PtmLocalizationQualityMetric(FrozenModel):
    role: PtmLocalizationRawInputRole
    metric_code: PtmLocalizationQualityMetricCode
    observation_state: PtmLocalizationQualityObservationState
    status: PtmLocalizationQualityMetricStatus
    required: bool
    numerator: int | None = Field(default=None, ge=0, le=M0504_MAX_COUNT)
    denominator: int | None = Field(default=None, ge=0, le=M0504_MAX_COUNT)
    value_ppm: int | None = Field(default=None, ge=0, le=M0504_RATE_SCALE)
    unit: Literal["ppm_fraction"] = "ppm_fraction"
    censored_count: int = Field(ge=0, le=M0504_MAX_COUNT)
    provenance: PtmLocalizationQualityMetricProvenance

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> PtmLocalizationQualityMetric:
        evaluable = self.observation_state in {
            PtmLocalizationQualityObservationState.OBSERVED,
            PtmLocalizationQualityObservationState.CENSORED,
        }
        if not evaluable:
            expected = (
                PtmLocalizationQualityMetricStatus.NOT_APPLICABLE
                if self.observation_state is PtmLocalizationQualityObservationState.NOT_APPLICABLE
                else PtmLocalizationQualityMetricStatus.NOT_EVALUABLE
            )
            if (
                self.numerator is not None
                or self.denominator is not None
                or self.value_ppm is not None
                or self.censored_count != 0
                or self.status is not expected
            ):
                raise ValueError("non-observed quality metrics cannot carry a ratio")
            return self
        if self.numerator is None or self.denominator is None:
            raise ValueError("observed quality metrics require numerator and denominator")
        if self.numerator > self.denominator:
            raise ValueError("quality metric numerator cannot exceed its denominator")
        if self.denominator == 0:
            if (
                self.value_ppm is not None
                or self.status is not PtmLocalizationQualityMetricStatus.NOT_EVALUABLE
            ):
                raise ValueError("zero-denominator quality metric must remain not evaluable")
        else:
            expected_value = (
                self.numerator * M0504_RATE_SCALE + self.denominator // 2
            ) // self.denominator
            if self.value_ppm != expected_value:
                raise ValueError("quality metric value must use exact round-half-up integer ppm")
        if (self.observation_state is PtmLocalizationQualityObservationState.CENSORED) != (
            self.censored_count > 0
        ):
            raise ValueError("censored state must exactly retain a positive censored count")
        if self.observation_state is PtmLocalizationQualityObservationState.CENSORED and (
            self.metric_code is not PtmLocalizationQualityMetricCode.DETECTION_LIMIT_BURDEN
            or self.censored_count != self.numerator
        ):
            raise ValueError("only detection burden may be censored with its exact numerator")
        return self


class PtmLocalizationQualityFinding(FrozenModel):
    finding_id: Identifier
    code: PtmLocalizationQualityFindingCode
    action: PtmLocalizationQualityFindingAction
    roles: tuple[PtmLocalizationRawInputRole, ...] = Field(default=(), max_length=M0504_ROLE_COUNT)
    metric_codes: tuple[PtmLocalizationQualityMetricCode, ...] = Field(
        default=(), max_length=M0504_METRIC_COUNT
    )
    message: NonEmptyStr

    @model_validator(mode="after")
    def finding_is_closed(self) -> PtmLocalizationQualityFinding:
        if len(self.roles) != len(set(self.roles)) or len(self.metric_codes) != len(
            set(self.metric_codes)
        ):
            raise ValueError("finding references must be unique")
        if self != finding_for(self.code, self.roles, self.metric_codes):
            raise ValueError("M05-04 finding contradicts its closed vocabulary")
        return self


class PtmLocalizationAssayQualityResult(FrozenModel):
    role: PtmLocalizationRawInputRole
    input_id: Identifier
    validated_input_digest: Sha256Digest
    document_digest: Sha256Digest
    profile_id: Identifier
    profile_version: SemanticVersion
    profile_digest: Sha256Digest
    role_fact_digest: Sha256Digest
    metrics: tuple[PtmLocalizationQualityMetric, ...] = Field(
        min_length=M0504_METRIC_COUNT, max_length=M0504_METRIC_COUNT
    )
    finding_codes: tuple[PtmLocalizationQualityFindingCode, ...] = Field(
        default=(), max_length=M0504_MAX_FINDINGS
    )
    disposition: PtmLocalizationQualityDisposition

    @field_validator("metrics")
    @classmethod
    def metrics_are_canonical(
        cls, values: tuple[PtmLocalizationQualityMetric, ...]
    ) -> tuple[PtmLocalizationQualityMetric, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("finding_codes")
    @classmethod
    def finding_codes_are_canonical(
        cls, values: tuple[PtmLocalizationQualityFindingCode, ...]
    ) -> tuple[PtmLocalizationQualityFindingCode, ...]:
        if len(values) != len(set(values)):
            raise ValueError("assay quality finding codes must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def assay_quality_is_closed(self) -> PtmLocalizationAssayQualityResult:
        opaque_ptm_localization_raw_input_identifier("input", self.input_id)
        opaque_ptm_localization_quality_identifier("profile", self.profile_id)
        codes = tuple(item.metric_code for item in self.metrics)
        if len(codes) != len(set(codes)) or set(codes) != set(PtmLocalizationQualityMetricCode):
            raise ValueError("assay quality requires all eight exact metrics")
        if any(item.role is not self.role for item in self.metrics):
            raise ValueError("assay quality metrics must retain one exact role")
        if self.disposition is not _disposition_for_finding_codes(self.finding_codes):
            raise ValueError("assay quality disposition contradicts its finding codes")
        return self


class PtmLocalizationQualityComputationReceipt(FrozenModel):
    raw_input_result_digest: Sha256Digest
    raw_input_receipt_digest: Sha256Digest
    raw_input_request_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    reference_bundle_digest: Sha256Digest
    assay_specimen_policy_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    fact_ledger_digest: Sha256Digest | None = None
    selected_profile_digests: tuple[Sha256Digest, ...] = Field(
        default=(), max_length=M0504_ROLE_COUNT
    )
    assay_quality_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=M0504_ROLE_COUNT)
    finding_codes: tuple[PtmLocalizationQualityFindingCode, ...] = Field(
        default=(), max_length=M0504_MAX_FINDINGS
    )
    parent_target: Literal["variant_peptide"] = M0504_PARENT
    emits_variant_peptide: Literal[False] = False
    disposition: PtmLocalizationQualityDisposition
    receipt_digest: Sha256Digest

    @field_validator("selected_profile_digests", "assay_quality_digests", "finding_codes")
    @classmethod
    def receipt_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if len(values) != len(set(values)):
            raise ValueError("receipt collections must be unique")
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_is_closed(self) -> PtmLocalizationQualityComputationReceipt:
        expected_count = M0504_ROLE_COUNT if self.fact_ledger_digest is not None else 0
        if len(self.selected_profile_digests) not in {0, expected_count} or len(
            self.assay_quality_digests
        ) not in {0, expected_count}:
            raise ValueError("receipt profile and assay-quality regions must be zero or four")
        if len(self.selected_profile_digests) != len(self.assay_quality_digests):
            raise ValueError("receipt profile and assay-quality regions must have equal lengths")
        if self.receipt_digest != receipt_digest(self):
            raise ValueError("M05-04 receipt digest does not match its canonical content")
        if self.disposition is not _disposition_for_finding_codes(self.finding_codes):
            raise ValueError("receipt disposition contradicts its finding codes")
        return self


class PtmLocalizationQualityResult(NonInferenceResultModel):
    output_type: Literal["ptm_localization_quality_profile"] = "ptm_localization_quality_profile"
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0504_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    receipt_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ComputePtmLocalizationQualityMetricsRequest
    receipt: PtmLocalizationQualityComputationReceipt
    assay_quality: tuple[PtmLocalizationAssayQualityResult, ...] = Field(
        default=(), max_length=M0504_ROLE_COUNT
    )
    findings: tuple[PtmLocalizationQualityFinding, ...] = Field(
        default=(), max_length=M0504_MAX_FINDINGS
    )
    disposition: PtmLocalizationQualityDisposition
    parent_target: Literal["variant_peptide"] = M0504_PARENT
    emits_variant_peptide: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_ptm_localization: Literal[False] = False
    infers_isoform: Literal[False] = False
    localizes_modification: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_cn_to_protein_regression: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    executes_model: Literal[False] = False
    persists_events: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=M0504_MIN_EVIDENCE, max_length=M0504_MAX_EVIDENCE
    )
    limitations: tuple[Limitation, ...] = Field(
        min_length=M0504_LIMITATION_COUNT, max_length=M0504_LIMITATION_COUNT
    )
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("request", mode="wrap")
    @classmethod
    def request_may_reuse_sealed_validation(
        cls,
        value: object,
        handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> ComputePtmLocalizationQualityMetricsRequest:
        capability = (
            info.context.get(_REQUEST_CAPABILITY_CONTEXT_KEY)
            if isinstance(info.context, dict)
            else None
        )
        if (
            isinstance(capability, _ValidatedRequestCapability)
            and capability.seal is _VALIDATION_CAPABILITY_SEAL
            and _request_capability_is_issued(capability)
            and value is capability.request
        ):
            return capability.request
        if info.mode == "json":
            return TypeAdapter(ComputePtmLocalizationQualityMetricsRequest).validate_json(
                canonical_json_bytes(value), strict=True
            )
        return cast("ComputePtmLocalizationQualityMetricsRequest", handler(value))

    @field_validator("assay_quality", "findings", "evidence", "limitations")
    @classmethod
    def semantic_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

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

    @field_validator("uncertainty")
    @classmethod
    def uncertainty_is_canonical(cls, value: UncertaintyProfile) -> UncertaintyProfile:
        return value.model_copy(
            update={"sensitivity_notes": tuple(sorted(value.sensitivity_notes))}
        )

    @model_validator(mode="after")
    def result_is_exact_replay(self, info: ValidationInfo) -> PtmLocalizationQualityResult:
        capability = (
            info.context.get(_REQUEST_CAPABILITY_CONTEXT_KEY)
            if isinstance(info.context, dict)
            else None
        )
        return _validate_result_replay(
            self,
            capability if isinstance(capability, _ValidatedRequestCapability) else None,
        )


def _raw_input_value(candidate: object) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        return dict.get(cast("dict[object, object]", candidate), "raw_input_result")
    if FrozenModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        return dict.get(storage, "raw_input_result")
    raise TypeError("M05-04 sealed validation requires an exact model or built-in dict family")


def _materialize_raw_input_value(candidate: object) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        if type(storage) is not dict or any(type(key) is not str for key in dict.keys(storage)):
            raise TypeError("M05-04 raw-input model storage must have exact string keys")
        return {
            key: _materialize_raw_input_value(dict.__getitem__(storage, key))
            for key in dict.keys(storage)
        }
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if any(type(key) is not str for key in dict.keys(mapping)):
            raise TypeError("M05-04 raw-input objects must have exact string keys")
        return {
            key: _materialize_raw_input_value(dict.__getitem__(mapping, key))
            for key in dict.keys(mapping)
        }
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        return [_materialize_raw_input_value(item) for item in list.__iter__(list_values)]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        return tuple(_materialize_raw_input_value(item) for item in tuple.__iter__(tuple_values))
    return candidate


def _raw_input_semantic_bytes(candidate: object) -> bytes:
    return canonical_json_bytes(_materialize_raw_input_value(candidate))


def _issue_raw_input_replay_capability(candidate: object) -> _RawInputReplayCapability:
    raw_value = _raw_input_value(candidate)
    source_bytes = _raw_input_semantic_bytes(raw_value)
    raw_value_mro = type.__getattribute__(type(raw_value), "__mro__")
    if type(raw_value) is not PtmLocalizationRawInputValidationResult and dict not in raw_value_mro:
        raise TypeError("M05-04 raw-input replay requires an exact result or built-in dict family")
    adapter = TypeAdapter(PtmLocalizationRawInputValidationResult)
    if type(raw_value) is PtmLocalizationRawInputValidationResult:
        replayed = adapter.validate_python(raw_value, strict=True)
        normalized_bytes = canonical_json_bytes(normalized_m0503_result(replayed))
    else:
        replayed = adapter.validate_json(source_bytes, strict=True)
        normalized_bytes = canonical_json_bytes(normalized_m0503_result(replayed))
    capability = _RawInputReplayCapability(
        seal=_VALIDATION_CAPABILITY_SEAL,
        source_bytes=source_bytes,
        normalized_bytes=normalized_bytes,
        result=replayed,
    )
    _ISSUED_RAW_CAPABILITIES[capability] = (
        capability.source_bytes,
        capability.normalized_bytes,
        capability.result,
    )
    return capability


def _validate_request_with_capability(candidate: object) -> _ValidatedRequestCapability:
    """Strictly replay and canonicalize one request before issuing an identity-bound cap."""

    raw_capability = _issue_raw_input_replay_capability(candidate)
    return _validate_request_with_raw_capability(candidate, raw_capability)


def _validate_request_with_raw_capability(
    candidate: object,
    raw_capability: _RawInputReplayCapability,
) -> _ValidatedRequestCapability:
    """Validate a request using only an exact already-replayed upstream capability."""

    if (
        raw_capability.seal is not _VALIDATION_CAPABILITY_SEAL
        or not _raw_capability_is_issued(raw_capability)
        or _raw_input_semantic_bytes(_raw_input_value(candidate))
        not in {raw_capability.source_bytes, raw_capability.normalized_bytes}
    ):
        raise TypeError("invalid or mismatched M05-04 raw-input replay capability")
    context = {_RAW_CAPABILITY_CONTEXT_KEY: raw_capability}
    adapter = TypeAdapter(ComputePtmLocalizationQualityMetricsRequest)
    validated = adapter.validate_python(candidate, strict=True, context=context)
    canonical = adapter.validate_json(
        canonical_json_bytes(normalized_request(validated)),
        strict=True,
        context=context,
    )
    capability = _ValidatedRequestCapability(
        seal=_VALIDATION_CAPABILITY_SEAL,
        request=canonical,
        request_digest=canonical_request_digest(canonical),
        policy_digest=policy_digest(canonical.policy),
        configuration_digest=configuration_digest(canonical.policy),
    )
    _ISSUED_REQUEST_CAPABILITIES[capability] = (
        capability.request,
        capability.request_digest,
        capability.policy_digest,
        capability.configuration_digest,
    )
    return capability


def _validate_json_request_with_raw_capability(
    serialized: bytes | bytearray | str,
    decoded: object,
    raw_capability: _RawInputReplayCapability,
) -> _ValidatedRequestCapability:
    """Validate a duplicate-free decoded JSON request using its exact replayed upstream cap."""

    if (
        raw_capability.seal is not _VALIDATION_CAPABILITY_SEAL
        or not _raw_capability_is_issued(raw_capability)
        or _raw_input_semantic_bytes(_raw_input_value(decoded))
        not in {raw_capability.source_bytes, raw_capability.normalized_bytes}
    ):
        raise TypeError("invalid or mismatched M05-04 raw-input replay capability")
    context = {_RAW_CAPABILITY_CONTEXT_KEY: raw_capability}
    adapter = TypeAdapter(ComputePtmLocalizationQualityMetricsRequest)
    validated = adapter.validate_json(serialized, strict=True, context=context)
    canonical = adapter.validate_json(
        canonical_json_bytes(normalized_request(validated)),
        strict=True,
        context=context,
    )
    capability = _ValidatedRequestCapability(
        seal=_VALIDATION_CAPABILITY_SEAL,
        request=canonical,
        request_digest=canonical_request_digest(canonical),
        policy_digest=policy_digest(canonical.policy),
        configuration_digest=configuration_digest(canonical.policy),
    )
    _ISSUED_REQUEST_CAPABILITIES[capability] = (
        capability.request,
        capability.request_digest,
        capability.policy_digest,
        capability.configuration_digest,
    )
    return capability


def _validate_result_with_capability(
    value: object,
    capability: _ValidatedRequestCapability,
) -> PtmLocalizationQualityResult:
    """Perform one final public result validation with an exact sealed request identity."""

    if capability.seal is not _VALIDATION_CAPABILITY_SEAL or not _request_capability_is_issued(
        capability
    ):
        raise TypeError("invalid M05-04 request-validation capability")
    return TypeAdapter(PtmLocalizationQualityResult).validate_python(
        value,
        strict=True,
        context={_REQUEST_CAPABILITY_CONTEXT_KEY: capability},
    )


def _disposition_for_finding_codes(
    codes: tuple[PtmLocalizationQualityFindingCode, ...],
) -> PtmLocalizationQualityDisposition:
    actions = {_ACTION_BY_FINDING[code] for code in codes}
    if PtmLocalizationQualityFindingAction.QUARANTINE in actions:
        return PtmLocalizationQualityDisposition.QUARANTINED
    if PtmLocalizationQualityFindingAction.ABSTAIN in actions:
        return PtmLocalizationQualityDisposition.ABSTAINED
    return PtmLocalizationQualityDisposition.QUALIFIED


def finding_for(
    code: PtmLocalizationQualityFindingCode,
    roles: tuple[PtmLocalizationRawInputRole, ...] = (),
    metric_codes: tuple[PtmLocalizationQualityMetricCode, ...] = (),
) -> PtmLocalizationQualityFinding:
    """Build one canonical finding from its closed code and affected dimensions."""

    ordered_roles = tuple(sorted(set(roles)))
    ordered_metrics = tuple(sorted(set(metric_codes)))
    digest = sha256_digest({"code": code, "roles": ordered_roles, "metric_codes": ordered_metrics})
    return PtmLocalizationQualityFinding.model_construct(
        finding_id=(f"finding.m0504.{code.value}.{digest.removeprefix('sha256:')[:16]}"),
        code=code,
        action=_ACTION_BY_FINDING[code],
        roles=ordered_roles,
        metric_codes=ordered_metrics,
        message=_MESSAGE_BY_FINDING[code],
    )


def _validated_input_by_role(
    request: ComputePtmLocalizationQualityMetricsRequest,
) -> dict[PtmLocalizationRawInputRole, object]:
    return {item.role: item for item in request.raw_input_result.validated_inputs}


def _ledger_bindings_close(request: ComputePtmLocalizationQualityMetricsRequest) -> bool:
    from glio_proteogen.contracts.m05_03 import validated_input_digest  # noqa: PLC0415

    ledger = request.fact_ledger
    upstream = request.raw_input_result
    if ledger is None:
        return False
    if (
        ledger.raw_input_result_digest != upstream.result_digest
        or ledger.raw_input_receipt_digest != upstream.receipt.receipt_digest
    ):
        return False
    inputs = {item.role: item for item in upstream.validated_inputs}
    if set(inputs) != set(PtmLocalizationRawInputRole):
        return False
    for fact in ledger.role_facts:
        source = inputs.get(fact.role)
        if source is None or (
            fact.input_id != source.document.input_id
            or fact.validated_input_digest != validated_input_digest(source)
            or fact.document_digest != source.document_digest
        ):
            return False
    return True


def _profile_candidates(
    request: ComputePtmLocalizationQualityMetricsRequest,
    role: PtmLocalizationRawInputRole,
) -> tuple[PtmLocalizationAssayQualityProfile, ...]:
    ledger = request.fact_ledger
    if ledger is None:
        return ()
    facts = {item.role: item for item in ledger.role_facts}
    inputs = {item.role: item for item in request.raw_input_result.validated_inputs}
    fact = facts[role]
    source = inputs[role]
    assay_kind = cast(
        "PtmLocalizationAssayKind | None",
        getattr(source.document, "assay_kind", None),
    )
    support_domain = cast(
        "PtmLocalizationSupportDomain | None",
        getattr(source.document, "support_domain", None),
    )
    controls_applicable = fact.counts.control_expected_count > 0
    return tuple(
        profile
        for profile in request.policy.profiles
        if profile.role is role
        and profile.assay_kind is assay_kind
        and profile.support_domain is support_domain
        and profile.controls_applicable is controls_applicable
    )


def matching_quality_profiles(
    request: ComputePtmLocalizationQualityMetricsRequest,
) -> tuple[PtmLocalizationAssayQualityProfile, ...]:
    """Select exactly one reviewed profile per role or return the safe-failure empty shape."""

    if (
        request.raw_input_result.disposition is not PtmLocalizationRawInputDisposition.VALIDATED
        or not _ledger_bindings_close(request)
    ):
        return ()
    inputs = {item.role: item for item in request.raw_input_result.validated_inputs}
    selected: list[PtmLocalizationAssayQualityProfile] = []
    for role in PtmLocalizationRawInputRole:
        source = inputs[role]
        matches = tuple(
            profile
            for profile in _profile_candidates(request, role)
            if source.document.assay_protocol_version in profile.approved_assay_protocol_versions
            and source.document.specimen_processing_version
            in profile.approved_specimen_processing_versions
            and source.document.unit_system_version in profile.approved_unit_system_versions
        )
        if len(matches) != 1:
            return ()
        selected.append(matches[0])
    return tuple(sorted(selected, key=canonical_json_bytes))


def _status_for_ratio(  # noqa: PLR0911 - direct closed threshold matrix.
    numerator: int,
    denominator: int,
    threshold: PtmLocalizationQualityThreshold,
) -> PtmLocalizationQualityMetricStatus:
    if denominator == 0:
        return PtmLocalizationQualityMetricStatus.NOT_EVALUABLE
    value_ppm = (numerator * M0504_RATE_SCALE + denominator // 2) // denominator
    if threshold.direction is PtmLocalizationQualityMetricDirection.AT_LEAST:
        if value_ppm >= threshold.pass_threshold_ppm:
            return PtmLocalizationQualityMetricStatus.PASS
        if value_ppm >= threshold.warning_threshold_ppm:
            return PtmLocalizationQualityMetricStatus.WARNING
        return PtmLocalizationQualityMetricStatus.FAIL
    if value_ppm <= threshold.pass_threshold_ppm:
        return PtmLocalizationQualityMetricStatus.PASS
    if value_ppm <= threshold.warning_threshold_ppm:
        return PtmLocalizationQualityMetricStatus.WARNING
    return PtmLocalizationQualityMetricStatus.FAIL


def _derive_quality_metrics(
    request: ComputePtmLocalizationQualityMetricsRequest,
    profiles: tuple[PtmLocalizationAssayQualityProfile, ...],
) -> tuple[PtmLocalizationQualityMetric, ...]:
    ledger = request.fact_ledger
    if ledger is None or len(profiles) != M0504_ROLE_COUNT or not _ledger_bindings_close(request):
        return ()
    profile_by_role = {item.role: item for item in profiles}
    facts_by_role = {item.role: item for item in ledger.role_facts}
    metrics: list[PtmLocalizationQualityMetric] = []
    ledger_hash = fact_ledger_digest(ledger)
    upstream = request.raw_input_result
    for role in PtmLocalizationRawInputRole:
        profile = profile_by_role[role]
        fact = facts_by_role[role]
        thresholds = {item.metric_code: item for item in profile.thresholds}
        for code in PtmLocalizationQualityMetricCode:
            threshold = thresholds[code]
            state = cast("PtmLocalizationQualityObservationState", getattr(fact.states, code.value))
            numerator_field, denominator_field = _COUNT_FIELDS_BY_METRIC[code]
            raw_numerator = cast("int", getattr(fact.counts, numerator_field))
            raw_denominator = cast("int", getattr(fact.counts, denominator_field))
            evaluable = state in {
                PtmLocalizationQualityObservationState.OBSERVED,
                PtmLocalizationQualityObservationState.CENSORED,
            }
            numerator = raw_numerator if evaluable else None
            denominator = raw_denominator if evaluable else None
            value_ppm = (
                (raw_numerator * M0504_RATE_SCALE + raw_denominator // 2) // raw_denominator
                if evaluable and raw_denominator > 0
                else None
            )
            status = (
                _status_for_ratio(raw_numerator, raw_denominator, threshold)
                if evaluable
                else (
                    PtmLocalizationQualityMetricStatus.NOT_APPLICABLE
                    if state is PtmLocalizationQualityObservationState.NOT_APPLICABLE
                    else PtmLocalizationQualityMetricStatus.NOT_EVALUABLE
                )
            )
            metrics.append(
                PtmLocalizationQualityMetric(
                    role=role,
                    metric_code=code,
                    observation_state=state,
                    status=status,
                    required=threshold.required,
                    numerator=numerator,
                    denominator=denominator,
                    value_ppm=value_ppm,
                    censored_count=(
                        fact.counts.below_detection_limit_count
                        if state is PtmLocalizationQualityObservationState.CENSORED
                        else 0
                    ),
                    provenance=PtmLocalizationQualityMetricProvenance(
                        raw_input_result_digest=upstream.result_digest,
                        raw_input_receipt_digest=upstream.receipt.receipt_digest,
                        fact_ledger_digest=ledger_hash,
                        role_fact_digest=role_facts_digest(fact),
                        profile_digest=profile_digest(profile),
                        threshold_digest=threshold_digest(threshold),
                        validated_input_digest=fact.validated_input_digest,
                        document_digest=fact.document_digest,
                    ),
                )
            )
    return tuple(sorted(metrics, key=canonical_json_bytes))


def _version_mismatch_findings(
    request: ComputePtmLocalizationQualityMetricsRequest,
) -> tuple[PtmLocalizationQualityFinding, ...]:
    if request.fact_ledger is None or not _ledger_bindings_close(request):
        return ()
    inputs = {item.role: item for item in request.raw_input_result.validated_inputs}
    findings: list[PtmLocalizationQualityFinding] = []
    for role in PtmLocalizationRawInputRole:
        candidates = _profile_candidates(request, role)
        if not candidates:
            continue
        document = inputs[role].document
        checks = (
            (
                document.assay_protocol_version,
                "approved_assay_protocol_versions",
                PtmLocalizationQualityFindingCode.ASSAY_PROTOCOL_VERSION_MISMATCH,
            ),
            (
                document.specimen_processing_version,
                "approved_specimen_processing_versions",
                PtmLocalizationQualityFindingCode.SPECIMEN_PROCESSING_VERSION_MISMATCH,
            ),
            (
                document.unit_system_version,
                "approved_unit_system_versions",
                PtmLocalizationQualityFindingCode.UNIT_SYSTEM_VERSION_MISMATCH,
            ),
        )
        for version, field, code in checks:
            if not any(version in getattr(profile, field) for profile in candidates):
                findings.append(finding_for(code, roles=(role,)))
    return tuple(sorted(findings, key=canonical_json_bytes))


def _cross_metric_roles(
    request: ComputePtmLocalizationQualityMetricsRequest,
) -> tuple[PtmLocalizationRawInputRole, ...]:
    ledger = request.fact_ledger
    if ledger is None:
        return ()
    return tuple(
        sorted(
            fact.role
            for fact in ledger.role_facts
            if (
                fact.counts.reference_eligible_count > fact.counts.observed_feature_count
                or fact.counts.detection_eligible_count > fact.counts.observed_feature_count
            )
        )
    )


def _derive_quality_findings(  # noqa: PLR0912 - explicit closed finding matrix.
    request: ComputePtmLocalizationQualityMetricsRequest,
    metrics: tuple[PtmLocalizationQualityMetric, ...],
    profiles: tuple[PtmLocalizationAssayQualityProfile, ...],
) -> tuple[PtmLocalizationQualityFinding, ...]:
    upstream = request.raw_input_result.disposition
    if upstream is PtmLocalizationRawInputDisposition.QUARANTINED:
        return (finding_for(PtmLocalizationQualityFindingCode.UPSTREAM_RAW_INPUTS_QUARANTINED),)
    if upstream is PtmLocalizationRawInputDisposition.ABSTAINED:
        return (finding_for(PtmLocalizationQualityFindingCode.UPSTREAM_RAW_INPUTS_ABSTAINED),)
    if not _ledger_bindings_close(request):
        return (finding_for(PtmLocalizationQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH),)
    if not profiles:
        versions = _version_mismatch_findings(request)
        return versions or (
            finding_for(PtmLocalizationQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED),
        )
    findings: list[PtmLocalizationQualityFinding] = []
    contradictory = _cross_metric_roles(request)
    if contradictory:
        findings.append(
            finding_for(
                PtmLocalizationQualityFindingCode.CROSS_METRIC_INCONSISTENCY,
                roles=contradictory,
                metric_codes=(
                    PtmLocalizationQualityMetricCode.ASSAY_FEATURE_COVERAGE,
                    PtmLocalizationQualityMetricCode.REFERENCE_MAPPING_COVERAGE,
                    PtmLocalizationQualityMetricCode.DETECTION_LIMIT_BURDEN,
                ),
            )
        )
    for metric in metrics:
        code: PtmLocalizationQualityFindingCode | None = None
        if (
            metric.required
            and metric.observation_state is PtmLocalizationQualityObservationState.MISSING
        ):
            code = PtmLocalizationQualityFindingCode.REQUIRED_METRIC_MISSING
        elif (
            metric.required
            and metric.observation_state is PtmLocalizationQualityObservationState.UNSUPPORTED
        ):
            code = PtmLocalizationQualityFindingCode.REQUIRED_METRIC_UNSUPPORTED
        elif metric.required and metric.status in {
            PtmLocalizationQualityMetricStatus.NOT_EVALUABLE,
            PtmLocalizationQualityMetricStatus.NOT_APPLICABLE,
        }:
            code = PtmLocalizationQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE
        elif metric.required and metric.status is PtmLocalizationQualityMetricStatus.WARNING:
            code = PtmLocalizationQualityFindingCode.REQUIRED_METRIC_WARNING
        elif metric.status is PtmLocalizationQualityMetricStatus.FAIL:
            code = PtmLocalizationQualityFindingCode.METRIC_THRESHOLD_FAILED
        elif not metric.required and metric.status is PtmLocalizationQualityMetricStatus.WARNING:
            code = PtmLocalizationQualityFindingCode.OPTIONAL_METRIC_WARNING
        if code is not None:
            findings.append(
                finding_for(
                    code,
                    roles=(metric.role,),
                    metric_codes=(metric.metric_code,),
                )
            )
    return tuple(sorted(findings, key=canonical_json_bytes))


def _derive_disposition(
    findings: tuple[PtmLocalizationQualityFinding, ...] = (),
) -> PtmLocalizationQualityDisposition:
    return _disposition_for_finding_codes(tuple(item.code for item in findings))


def _derive_assay_quality(
    request: ComputePtmLocalizationQualityMetricsRequest,
    metrics: tuple[PtmLocalizationQualityMetric, ...],
    findings: tuple[PtmLocalizationQualityFinding, ...],
    profiles: tuple[PtmLocalizationAssayQualityProfile, ...],
) -> tuple[PtmLocalizationAssayQualityResult, ...]:
    ledger = request.fact_ledger
    if (
        ledger is None
        or len(metrics) != M0504_COMPUTED_METRIC_COUNT
        or len(profiles) != M0504_ROLE_COUNT
    ):
        return ()
    by_role = {item.role: item for item in request.raw_input_result.validated_inputs}
    facts = {item.role: item for item in ledger.role_facts}
    profile_by_role = {item.role: item for item in profiles}
    values: list[PtmLocalizationAssayQualityResult] = []
    for role in PtmLocalizationRawInputRole:
        role_metrics = tuple(item for item in metrics if item.role is role)
        role_codes = tuple(
            sorted({item.code for item in findings if not item.roles or role in item.roles})
        )
        role_disposition = _disposition_for_finding_codes(role_codes)
        source = by_role[role]
        fact = facts[role]
        profile = profile_by_role[role]
        values.append(
            PtmLocalizationAssayQualityResult(
                role=role,
                input_id=source.document.input_id,
                validated_input_digest=fact.validated_input_digest,
                document_digest=fact.document_digest,
                profile_id=profile.profile_id,
                profile_version=profile.version,
                profile_digest=profile_digest(profile),
                role_fact_digest=role_facts_digest(fact),
                metrics=role_metrics,
                finding_codes=role_codes,
                disposition=role_disposition,
            )
        )
    return tuple(sorted(values, key=canonical_json_bytes))


def _derive_receipt(
    request: ComputePtmLocalizationQualityMetricsRequest,
    assay_quality: tuple[PtmLocalizationAssayQualityResult, ...],
    findings: tuple[PtmLocalizationQualityFinding, ...],
    disposition: PtmLocalizationQualityDisposition,
    profiles: tuple[PtmLocalizationAssayQualityProfile, ...],
) -> PtmLocalizationQualityComputationReceipt:
    upstream = request.raw_input_result
    payload: dict[str, object] = {
        "raw_input_result_digest": upstream.result_digest,
        "raw_input_receipt_digest": upstream.receipt.receipt_digest,
        "raw_input_request_digest": upstream.request_digest,
        "identity_resolution_digest": upstream.receipt.identity_resolution_digest,
        "protocol_result_digest": upstream.receipt.protocol_result_digest,
        "reference_bundle_digest": upstream.receipt.reference_bundle_digest,
        "assay_specimen_policy_digest": upstream.receipt.assay_specimen_policy_digest,
        "intended_use_evidence_digest": upstream.receipt.intended_use_evidence_digest,
        "policy_digest": policy_digest(request.policy),
        "configuration_digest": configuration_digest(request.policy),
        "fact_ledger_digest": (
            fact_ledger_digest(request.fact_ledger) if request.fact_ledger is not None else None
        ),
        "selected_profile_digests": tuple(sorted(profile_digest(item) for item in profiles)),
        "assay_quality_digests": tuple(
            sorted(assay_quality_digest(item) for item in assay_quality)
        ),
        "finding_codes": tuple(sorted({item.code for item in findings})),
        "parent_target": M0504_PARENT,
        "emits_variant_peptide": False,
        "disposition": disposition,
        "receipt_digest": _M0504_ZERO_DIGEST,
    }
    payload["receipt_digest"] = receipt_digest(payload)
    return PtmLocalizationQualityComputationReceipt.model_validate(payload, strict=True)


@dataclass(frozen=True, slots=True)
class _ExpectedQualityBundle:
    profiles: tuple[PtmLocalizationAssayQualityProfile, ...]
    metrics: tuple[PtmLocalizationQualityMetric, ...]
    findings: tuple[PtmLocalizationQualityFinding, ...]
    disposition: PtmLocalizationQualityDisposition
    assay_quality: tuple[PtmLocalizationAssayQualityResult, ...]
    receipt: PtmLocalizationQualityComputationReceipt
    support: SupportDecision


def _expected_quality_bundle(
    request: ComputePtmLocalizationQualityMetricsRequest,
) -> _ExpectedQualityBundle:
    """Derive all mutually dependent quality regions once from the full request."""

    profiles = matching_quality_profiles(request)
    metrics = _derive_quality_metrics(request, profiles)
    findings = _derive_quality_findings(request, metrics, profiles)
    disposition = _derive_disposition(findings)
    assay_quality = _derive_assay_quality(request, metrics, findings, profiles)
    receipt = _derive_receipt(request, assay_quality, findings, disposition, profiles)
    support = _derive_support(disposition, metrics)
    return _ExpectedQualityBundle(
        profiles=profiles,
        metrics=metrics,
        findings=findings,
        disposition=disposition,
        assay_quality=assay_quality,
        receipt=receipt,
        support=support,
    )


def _canonical_region(values: tuple[object, ...]) -> tuple[bytes, ...]:
    return tuple(sorted(canonical_json_bytes(item) for item in values))


def expected_quality_metrics(
    request: ComputePtmLocalizationQualityMetricsRequest,
    profiles: tuple[PtmLocalizationAssayQualityProfile, ...] | None = None,
) -> tuple[PtmLocalizationQualityMetric, ...]:
    """Project the exact metrics and reject any caller-forged profile override."""

    bundle = _expected_quality_bundle(request)
    if profiles is not None and _canonical_region(profiles) != _canonical_region(bundle.profiles):
        raise ValueError("supplied M05-04 profiles do not match exact profile selection")
    return bundle.metrics


def expected_quality_findings(
    request: ComputePtmLocalizationQualityMetricsRequest,
    metrics: tuple[PtmLocalizationQualityMetric, ...] = (),
) -> tuple[PtmLocalizationQualityFinding, ...]:
    """Recompute findings and reject any nonempty forged metric override."""

    bundle = _expected_quality_bundle(request)
    if metrics and _canonical_region(metrics) != _canonical_region(bundle.metrics):
        raise ValueError("supplied M05-04 metrics do not match exact metric projection")
    return bundle.findings


def expected_disposition(
    request: ComputePtmLocalizationQualityMetricsRequest,
    metrics: tuple[PtmLocalizationQualityMetric, ...] = (),
    findings: tuple[PtmLocalizationQualityFinding, ...] = (),
) -> PtmLocalizationQualityDisposition:
    """Recompute disposition and reject caller-forged derived regions."""

    bundle = _expected_quality_bundle(request)
    if metrics and _canonical_region(metrics) != _canonical_region(bundle.metrics):
        raise ValueError("supplied M05-04 metrics do not match exact metric projection")
    if findings and _canonical_region(findings) != _canonical_region(bundle.findings):
        raise ValueError("supplied M05-04 findings do not match exact finding projection")
    return bundle.disposition


def expected_assay_quality(
    request: ComputePtmLocalizationQualityMetricsRequest,
    metrics: tuple[PtmLocalizationQualityMetric, ...],
    findings: tuple[PtmLocalizationQualityFinding, ...],
) -> tuple[PtmLocalizationAssayQualityResult, ...]:
    """Recompute assay regions and reject caller-forged prerequisites."""

    bundle = _expected_quality_bundle(request)
    if _canonical_region(metrics) != _canonical_region(bundle.metrics):
        raise ValueError("supplied M05-04 metrics do not match exact metric projection")
    if _canonical_region(findings) != _canonical_region(bundle.findings):
        raise ValueError("supplied M05-04 findings do not match exact finding projection")
    return bundle.assay_quality


def expected_receipt(
    request: ComputePtmLocalizationQualityMetricsRequest,
    assay_quality: tuple[PtmLocalizationAssayQualityResult, ...],
    findings: tuple[PtmLocalizationQualityFinding, ...],
    disposition: PtmLocalizationQualityDisposition,
) -> PtmLocalizationQualityComputationReceipt:
    """Recompute the receipt and reject caller-forged derived regions."""

    bundle = _expected_quality_bundle(request)
    if _canonical_region(assay_quality) != _canonical_region(bundle.assay_quality):
        raise ValueError("supplied M05-04 assay quality does not match exact projection")
    if _canonical_region(findings) != _canonical_region(bundle.findings):
        raise ValueError("supplied M05-04 findings do not match exact finding projection")
    if disposition is not bundle.disposition:
        raise ValueError("supplied M05-04 disposition does not match exact precedence")
    return bundle.receipt


def _derive_support(
    disposition: PtmLocalizationQualityDisposition,
    metrics: tuple[PtmLocalizationQualityMetric, ...] = (),
) -> SupportDecision:
    optional_warning = any(
        item.status is PtmLocalizationQualityMetricStatus.WARNING and not item.required
        for item in metrics
    )
    if disposition is PtmLocalizationQualityDisposition.QUALIFIED and optional_warning:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="ptm_localization_quality_qualified_with_optional_warning",
            rationale="Required metrics passed; an optional warning limits support.",
        )
    if disposition is PtmLocalizationQualityDisposition.QUALIFIED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="ptm_localization_quality_qualified",
            rationale="All required aggregate ptm_localization quality metrics passed.",
        )
    if disposition is PtmLocalizationQualityDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="ptm_localization_quality_quarantined",
            rationale="A binding, version, consistency, or threshold outcome requires review.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="ptm_localization_quality_abstained",
        rationale="Upstream evidence or a required quality dimension is not evaluable.",
    )


def expected_support(request: ComputePtmLocalizationQualityMetricsRequest) -> SupportDecision:
    """Derive support only from the exact request-derived disposition and metrics."""

    return _expected_quality_bundle(request).support


def expected_uncertainty() -> UncertaintyProfile:
    rationales = (
        "Fixed-point aggregate facts provide no measurement-error distribution.",
        "Deterministic aggregate scoring estimates no sampling distribution.",
        "The deterministic evaluator fits no parameters.",
        "No learned or probabilistic model is executed.",
        "No protein, ptm_localization, or isoform identification is performed.",
        "Support is a deterministic reviewed-threshold decision.",
        "Transportability requires external site and assay validation.",
    )
    estimates = tuple(
        UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, probability=None, rationale=item)
        for item in rationales
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
                    "Missing, unsupported, indeterminate, and censored evidence never becomes "
                    "negative.",
                    "Reviewed profile or threshold changes may change disposition without "
                    "changing source evidence.",
                )
            )
        ),
    )


def _control_decisions(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
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
    return tuple(sorted(records, key=canonical_json_bytes))


def quality_evidence_index(
    request: ComputePtmLocalizationQualityMetricsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    ledger = request.fact_ledger
    artifacts: tuple[ArtifactReference, ...] = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
        *(item.evidence for item in request.policy.profiles),
        *((ledger.evidence,) if ledger is not None else ()),
        *((item.evidence for item in ledger.role_facts) if ledger is not None else ()),
    )
    if not M0504_MIN_EVIDENCE <= len(artifacts) <= M0504_MAX_EVIDENCE:
        raise ValueError("M05-04 evidence index exceeds its exact installed shape")
    _require_consistent_evidence_identities(artifacts)
    return tuple(
        sorted(
            (
                EvidenceReference(reference=item, role="evidence", claim=M0504_EVIDENCE_CLAIM)
                for item in artifacts
            ),
            key=canonical_json_bytes,
        )
    )


def _derive_provenance(  # noqa: PLR0913 - optional sealed digest cache is explicit.
    request: ComputePtmLocalizationQualityMetricsRequest,
    metrics: tuple[PtmLocalizationQualityMetric, ...],
    receipt: PtmLocalizationQualityComputationReceipt,
    *,
    request_hash: Sha256Digest | None = None,
    policy_hash: Sha256Digest | None = None,
    config_hash: Sha256Digest | None = None,
) -> ProvenanceRecord:
    request_hash = request_hash or canonical_request_digest(request)
    policy_hash = policy_hash or policy_digest(request.policy)
    config_hash = config_hash or configuration_digest(request.policy)
    controls = _control_decisions(request.context)
    evidence = quality_evidence_index(request)
    upstream = request.raw_input_result
    ledger = request.fact_ledger
    digests: set[Sha256Digest] = {
        request_hash,
        upstream.result_digest,
        upstream.receipt.receipt_digest,
        upstream.request_digest,
        policy_hash,
        config_hash,
        *(item.document_digest for item in upstream.validated_inputs),
        *(sha256_digest(item) for item in upstream.validated_inputs),
        *(item.reference.digest for item in evidence),
        *(item.evidence_digest for item in controls),
        *(metric_digest(item) for item in metrics),
    }
    if ledger is not None:
        digests.add(fact_ledger_digest(ledger))
        digests.update(role_facts_digest(item) for item in ledger.role_facts)
    digests.update(profile_digest(item) for item in matching_quality_profiles(request))
    digests.add(receipt.receipt_digest)
    if request.supersedes_result_digest is not None:
        digests.add(request.supersedes_result_digest)
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m0504.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0504_MODULE_ID,
        module_version=M0504_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(digests)),
        configuration_digest=config_hash,
        consent_decision_id=refs.consent.decision_id,
        consent_state=ConsentState.GRANTED,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def expected_provenance(
    request: ComputePtmLocalizationQualityMetricsRequest,
    metrics: tuple[PtmLocalizationQualityMetric, ...] = (),
    receipt: PtmLocalizationQualityComputationReceipt | None = None,
) -> ProvenanceRecord:
    """Recompute provenance and reject caller-forged optional derived regions."""

    bundle = _expected_quality_bundle(request)
    if metrics and _canonical_region(metrics) != _canonical_region(bundle.metrics):
        raise ValueError("supplied M05-04 metrics do not match exact metric projection")
    if receipt is not None and receipt != bundle.receipt:
        raise ValueError("supplied M05-04 receipt does not match exact receipt projection")
    return _derive_provenance(request, bundle.metrics, bundle.receipt)


def expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code="deterministic_aggregate_quality_metrics_only",
                    statement=(
                        "This result computes deterministic metrics from caller-declared "
                        "aggregate facts only."
                    ),
                ),
                Limitation(
                    code="external_measurements_controls_and_authority_not_authenticated",
                    statement=(
                        "External measurements, controls, and caller-declared authorities are "
                        "not authenticated."
                    ),
                ),
                Limitation(
                    code="no_ptm_localization_or_clinical_inference",
                    statement=(
                        "No PTM localization, variant peptide, kinase activity, treatment, or "
                        "clinical inference is produced."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def _normalized_model(value: object) -> object:
    if hasattr(value, "model_dump"):
        return cast("FrozenModel", value).model_dump(mode="python", exclude_none=False)
    return value


def _validate_result_replay(
    self: PtmLocalizationQualityResult,
    capability: _ValidatedRequestCapability | None = None,
) -> PtmLocalizationQualityResult:
    metrics = tuple(item for assay in self.assay_quality for item in assay.metrics)
    bundle = _expected_quality_bundle(self.request)
    replay_metrics = bundle.metrics
    replay_findings = bundle.findings
    replay_disposition = bundle.disposition
    replay_assay = bundle.assay_quality
    replay_receipt = bundle.receipt
    sealed = (
        capability is not None
        and capability.seal is _VALIDATION_CAPABILITY_SEAL
        and _request_capability_is_issued(capability)
        and capability.request is self.request
    )
    request_hash = (
        capability.request_digest
        if sealed and capability is not None
        else canonical_request_digest(self.request)
    )
    policy_hash = (
        capability.policy_digest
        if sealed and capability is not None
        else policy_digest(self.request.policy)
    )
    config_hash = (
        capability.configuration_digest
        if sealed and capability is not None
        else configuration_digest(self.request.policy)
    )
    expected_result_id = f"result.m0504.{request_hash.removeprefix('sha256:')}"
    if (
        tuple(sorted(self.assay_quality, key=canonical_json_bytes)) != replay_assay
        or tuple(sorted(metrics, key=canonical_json_bytes)) != replay_metrics
        or tuple(sorted(self.findings, key=canonical_json_bytes)) != replay_findings
        or self.disposition is not replay_disposition
        or self.receipt != replay_receipt
        or self.result_id != expected_result_id
        or self.request_digest != request_hash
        or self.policy_digest != policy_hash
        or self.configuration_digest != config_hash
        or self.receipt_digest != replay_receipt.receipt_digest
    ):
        raise ValueError("M05-04 result envelope does not replay from its full request")
    if self.completed_at != self.request.context.occurred_at:
        raise ValueError("M05-04 completion time must equal execution time")
    if self.support != bundle.support:
        raise ValueError("M05-04 support does not replay")
    if canonical_json_bytes(_normalized_model(self.uncertainty)) != canonical_json_bytes(
        _normalized_model(expected_uncertainty())
    ):
        raise ValueError("M05-04 uncertainty does not replay")
    if canonical_json_bytes(_normalized_model(self.provenance)) != canonical_json_bytes(
        _normalized_model(
            _derive_provenance(
                self.request,
                replay_metrics,
                replay_receipt,
                request_hash=request_hash,
                policy_hash=policy_hash,
                config_hash=config_hash,
            )
        )
    ):
        raise ValueError("M05-04 provenance does not replay")
    if tuple(sorted(self.evidence, key=canonical_json_bytes)) != quality_evidence_index(
        self.request
    ):
        raise ValueError("M05-04 evidence index does not replay")
    if tuple(sorted(self.limitations, key=canonical_json_bytes)) != expected_limitations():
        raise ValueError("M05-04 limitations do not replay")
    optional_warning = any(
        item.status is PtmLocalizationQualityMetricStatus.WARNING and not item.required
        for item in replay_metrics
    )
    if self.human_review_required != (
        replay_disposition is not PtmLocalizationQualityDisposition.QUALIFIED or optional_warning
    ):
        raise ValueError("M05-04 review flag contradicts disposition")
    if self.result_digest != result_payload_digest(self):
        raise ValueError("M05-04 result digest does not match its canonical payload")
    return self


__all__ = [name for name in globals() if name.startswith("M0504_")] + [
    "ComputePtmLocalizationQualityMetricsRequest",
    "PtmLocalizationAssayQualityProfile",
    "PtmLocalizationAssayQualityResult",
    "PtmLocalizationQualityComputationReceipt",
    "PtmLocalizationQualityDisposition",
    "PtmLocalizationQualityFactLedger",
    "PtmLocalizationQualityFinding",
    "PtmLocalizationQualityFindingAction",
    "PtmLocalizationQualityFindingCode",
    "PtmLocalizationQualityMetric",
    "PtmLocalizationQualityMetricCode",
    "PtmLocalizationQualityMetricDirection",
    "PtmLocalizationQualityMetricProvenance",
    "PtmLocalizationQualityMetricStatus",
    "PtmLocalizationQualityObservationState",
    "PtmLocalizationQualityOpaqueNamespace",
    "PtmLocalizationQualityPolicy",
    "PtmLocalizationQualityResult",
    "PtmLocalizationQualityRoleCounts",
    "PtmLocalizationQualityRoleFactStates",
    "PtmLocalizationQualityRoleFacts",
    "PtmLocalizationQualityThreshold",
    "expected_disposition",
    "expected_assay_quality",
    "expected_limitations",
    "expected_provenance",
    "expected_quality_findings",
    "expected_quality_metrics",
    "expected_receipt",
    "expected_support",
    "expected_uncertainty",
    "finding_for",
    "matching_quality_profiles",
    "opaque_ptm_localization_quality_identifier",
    "quality_evidence_index",
]
