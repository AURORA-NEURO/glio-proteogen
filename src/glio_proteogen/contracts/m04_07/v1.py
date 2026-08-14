"""Strict contracts for deterministic M04-07 joint support-envelope routing.

M04-07 consumes full, replay-validated M04-04 and M04-06 results and projects
privacy-minimized receipts from them.  It confirms support only when one
reviewed envelope admits the complete proteoform context; missing or unknown
declarations remain indeterminate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Any, Final, Literal, cast
from weakref import WeakKeyDictionary

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from glio_proteogen.contracts.m04_01 import ProteoformApplicability  # noqa: TC001
from glio_proteogen.contracts.m04_03 import ProteoformRawInputRole
from glio_proteogen.contracts.m04_04 import (
    ProteoformQualityDisposition,
    ProteoformQualityMetricCode,
    ProteoformQualityMetricStatus,
    ProteoformQualityObservationState,
    ProteoformQualityResult,
)
from glio_proteogen.contracts.m04_06 import (
    M0406_MAX_LEVELS_PER_FACTOR,
    M0406_MAX_TARGETS,
    ProteoformHarmonizationDisposition,
    ProteoformHarmonizationResult,
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
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0407_MODULE_ID: Final = "GLIO-PROTEOGEN-M04-07"
M0407_OPERATION: Final = "route_proteoform_support"
M0407_CONTRACT_VERSION: Final = "1.0.0"
M0407_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-07+json"
M0407_PARENT: Final = "protein_rna_discordance"
M0407_OWNER: Final = "Computational biology"
M0407_SAFETY_CLASS: Final = "S2"
M0407_GATE: Final = "G1"
M0407_RATE_SCALE: Final = 1_000_000
M0407_DIMENSION_COUNT: Final = 8
M0407_DECLARED_FACT_COUNT: Final = 4
M0407_CONTEXT_RECEIPT_COUNT: Final = 3
M0407_QUALITY_METRIC_COUNT: Final = 32
M0407_MAX_ENVELOPES: Final = 64
M0407_MAX_FACT_VALUES: Final = 64
M0407_MAX_PLATFORM_LEVEL_IDS: Final = M0406_MAX_LEVELS_PER_FACTOR
M0407_MAX_ANALYSIS_TARGETS: Final = M0406_MAX_TARGETS
_MAX_SHALLOW_MAPPING_ITEMS: Final = 512
M0407_MAX_APPROVED_VERSIONS: Final = 32
M0407_MAX_EVIDENCE_PER_FACT: Final = 8
# At maximum envelope capacity every dimension can be blocked, and both
# prerequisite modules can add one aggregate blocker.  The joint-envelope
# blocker is mutually exclusive with that shape because it requires the union
# of supported dimensions to cover the domain.
M0407_MAX_ABSTENTIONS: Final = (M0407_MAX_ENVELOPES * M0407_DIMENSION_COUNT) + 2
M0407_MAX_EVIDENCE: Final = 46
M0407_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0407_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0407_EVIDENCE_CLAIM: Final = (
    "Caller-declared evidence for deterministic proteoform support routing; "
    "issuer authority is not authenticated."
)
M0407_ROUTING_LIMITATION_CODE: Final = "proteoform_support_routing_only"
M0407_AUTHORITY_LIMITATION_CODE: Final = "external_receipt_issuers_unverified"
M0407_DOMAIN_LIMITATION_CODE: Final = "reviewed_support_domain_not_validated"
M0407_UNCERTAINTY_RATIONALES: Final = (
    "Support routing does not estimate measurement uncertainty.",
    "Support routing does not estimate sampling uncertainty.",
    "Support routing does not estimate parameter uncertainty.",
    "Support routing does not estimate model-form uncertainty.",
    "Support routing does not re-estimate upstream identification uncertainty.",
    "Support is categorical within one reviewed joint envelope.",
    "Transport beyond the reviewed support envelope is not estimable.",
)
M0407_SENSITIVITY_NOTES: Final = (
    "Missing and unknown declarations remain indeterminate.",
    "No union of partial envelopes can establish support.",
)

_M0404_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-04+json"
_M0406_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-06+json"
_VALIDATION_CAPABILITY_SEAL: Final = object()
_VALIDATION_CAPABILITY_LOCK: Final = RLock()
_PREREQUISITES_CAPABILITY_SNAPSHOT_LENGTH: Final = 4
_REQUEST_CAPABILITY_SNAPSHOT_LENGTH: Final = 9
_PREREQUISITES_CAPABILITY_CONTEXT_KEY: Final = "_m0407_prerequisites_replay_capability"
_PREREQUISITES_CAPABILITY_VERIFIED_KEY: Final = "_m0407_prerequisites_replay_verified"
_REQUEST_CAPABILITY_CONTEXT_KEY: Final = "_m0407_validated_request_capability"
_REQUEST_CAPABILITY_VERIFIED_KEY: Final = "_m0407_validated_request_verified"

_OPAQUE_IDENTIFIER = re.compile(
    r"^(request|profile|policy|envelope|specimen|disease|reference|use|reason|"
    r"remediation|evidence|reviewer|route)\.[0-9a-f]{64}$"
)
_OWNED_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


class ProteoformSupportDimension(StrEnum):
    ASSAY = "assay"
    SPECIMEN = "specimen"
    DISEASE_CLASS = "disease_class"
    QUALITY = "quality"
    COMPLETENESS = "completeness"
    PLATFORM = "platform"
    REFERENCE = "reference"
    INTENDED_USE = "intended_use"


class ProteoformDeclaredSupportState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN = "unknown"


class ProteoformDimensionSupportDecision(StrEnum):
    SUPPORTED = "supported"
    OUTSIDE_DOMAIN = "outside_domain"
    INDETERMINATE = "indeterminate"


class ProteoformEnvelopeSupportDecision(StrEnum):
    CONFIRMED = "confirmed"
    ELIMINATED = "eliminated"
    PROVISIONAL = "provisional"


class ProteoformSupportDisposition(StrEnum):
    SUPPORTED = "supported"
    ABSTAINED = "abstained"


class ProteoformContextRole(StrEnum):
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"
    TREATMENT_HISTORY = "treatment_history"


class ProteoformAbstentionCode(StrEnum):
    DIMENSION_OUTSIDE_DOMAIN = "dimension_outside_domain"
    DIMENSION_INDETERMINATE = "dimension_indeterminate"
    PREREQUISITE_UNRELEASABLE = "prerequisite_unreleasable"
    JOINT_COMBINATION_OUTSIDE_DOMAIN = "joint_combination_outside_domain"


class ProteoformRemediationPath(StrEnum):
    CORRECT_SUPPORT_DECLARATION = "correct_support_declaration"
    SUPPLY_REQUIRED_SUPPORT_EVIDENCE = "supply_required_support_evidence"
    RESOLVE_UPSTREAM_PREREQUISITE = "resolve_upstream_prerequisite"
    SELECT_ONE_REVIEWED_JOINT_ENVELOPE = "select_one_reviewed_joint_envelope"
    REQUEST_GOVERNED_SUPPORT_REVIEW = "request_governed_support_review"


def opaque_support_identifier(namespace: str, value: str) -> Identifier:
    """Validate one content-derived M04-07 identifier and its namespace."""

    if not value.startswith(f"{namespace}.") or _OPAQUE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"identifier must be an opaque {namespace} digest alias")
    return value


def _owned_evidence(value: ArtifactReference) -> ArtifactReference:
    opaque_support_identifier("evidence", value.artifact_id)
    if _OWNED_MEDIA_TYPE.fullmatch(value.media_type) is None:
        raise ValueError("M04-07 evidence media type must use lowercase type/subtype syntax")
    return value


class ProteoformQualityMetricSupportReceipt(FrozenModel):
    role: ProteoformRawInputRole
    metric_code: ProteoformQualityMetricCode
    observation_state: ProteoformQualityObservationState
    status: ProteoformQualityMetricStatus
    value_ppm: int | None = Field(default=None, ge=0, le=M0407_RATE_SCALE)

    @model_validator(mode="after")
    def value_matches_observation(self) -> ProteoformQualityMetricSupportReceipt:
        if self.observation_state in {
            ProteoformQualityObservationState.OBSERVED,
            ProteoformQualityObservationState.CENSORED,
        }:
            if self.value_ppm is None or self.status in {
                ProteoformQualityMetricStatus.NOT_EVALUABLE,
                ProteoformQualityMetricStatus.NOT_APPLICABLE,
            }:
                raise ValueError("evaluable quality support metric requires its integer value")
        elif self.value_ppm is not None or self.status is not (
            ProteoformQualityMetricStatus.NOT_APPLICABLE
            if self.observation_state is ProteoformQualityObservationState.NOT_APPLICABLE
            else ProteoformQualityMetricStatus.NOT_EVALUABLE
        ):
            raise ValueError("non-evaluable quality support metric cannot carry a value")
        return self


class ProteoformQualitySupportReceipt(FrozenModel):
    module_id: Literal["GLIO-PROTEOGEN-M04-04"] = "GLIO-PROTEOGEN-M04-04"
    receipt_version: Literal["1.0.0"] = M0407_CONTRACT_VERSION
    artifact_reference: ArtifactReference
    result_digest: Sha256Digest
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    disposition: ProteoformQualityDisposition
    support_status: SupportStatus
    human_review_required: bool
    completed_at: AwareDatetime
    identity_resolution_digest: Sha256Digest
    applicability: ProteoformApplicability | None = None
    assay_protocol_version: SemanticVersion
    specimen_processing_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    metrics: tuple[ProteoformQualityMetricSupportReceipt, ...] = Field(
        default=(), max_length=M0407_QUALITY_METRIC_COUNT
    )
    receipt_digest: Sha256Digest

    @field_validator("metrics")
    @classmethod
    def metrics_are_canonical(
        cls, values: tuple[ProteoformQualityMetricSupportReceipt, ...]
    ) -> tuple[ProteoformQualityMetricSupportReceipt, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_shape_is_closed(self) -> ProteoformQualitySupportReceipt:
        from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
            quality_support_receipt_digest,
        )

        metric_keys = tuple((item.role, item.metric_code) for item in self.metrics)
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError("quality support receipt metrics must be unique")
        expected_artifact_id = f"result.m0404.{self.request_digest.removeprefix('sha256:')}"
        if (
            self.artifact_reference.artifact_id != expected_artifact_id
            or self.artifact_reference.version != M0407_CONTRACT_VERSION
            or self.artifact_reference.media_type != _M0404_RESULT_MEDIA_TYPE
            or self.artifact_reference.digest != self.result_digest
        ):
            raise ValueError("quality receipt artifact does not bind the exact M04-04 result")
        if self.disposition is ProteoformQualityDisposition.QUALIFIED and (
            len(self.metrics) != M0407_QUALITY_METRIC_COUNT
            or set(metric_keys)
            != {
                (role, code)
                for role in ProteoformRawInputRole
                for code in ProteoformQualityMetricCode
            }
            or self.applicability is None
            or self.support_status not in {SupportStatus.SUPPORTED, SupportStatus.LIMITED}
            or any(
                item.status
                in {
                    ProteoformQualityMetricStatus.FAIL,
                    ProteoformQualityMetricStatus.NOT_EVALUABLE,
                }
                for item in self.metrics
            )
        ):
            raise ValueError("qualified quality receipt requires its exact metric domain")
        if self.disposition is not ProteoformQualityDisposition.QUALIFIED and (
            self.metrics or self.applicability is not None
        ):
            raise ValueError("non-qualified quality receipt cannot project quality values")
        expected_statuses, expected_review = {
            ProteoformQualityDisposition.QUALIFIED: (
                {SupportStatus.SUPPORTED, SupportStatus.LIMITED},
                {False, True},
            ),
            ProteoformQualityDisposition.QUARANTINED: (
                {SupportStatus.REVIEW_REQUIRED},
                {True},
            ),
            ProteoformQualityDisposition.ABSTAINED: (
                {SupportStatus.UNSUPPORTED},
                {True},
            ),
        }[self.disposition]
        if (
            self.support_status not in expected_statuses
            or self.human_review_required not in expected_review
        ):
            raise ValueError("quality receipt disposition and support envelope contradict")
        if self.receipt_digest != quality_support_receipt_digest(self):
            raise ValueError("quality support receipt digest does not match its content")
        return self


class ProteoformHarmonizationSupportReceipt(FrozenModel):
    module_id: Literal["GLIO-PROTEOGEN-M04-06"] = "GLIO-PROTEOGEN-M04-06"
    receipt_version: Literal["1.0.0"] = M0407_CONTRACT_VERSION
    artifact_reference: ArtifactReference
    result_digest: Sha256Digest
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    disposition: ProteoformHarmonizationDisposition
    support_status: SupportStatus
    human_review_required: bool
    completed_at: AwareDatetime
    quality_result_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    applicability: ProteoformApplicability | None = None
    assay_protocol_version: SemanticVersion
    specimen_processing_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    analysis_platform_level_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M0407_MAX_PLATFORM_LEVEL_IDS
    )
    analysis_target_count: int | None = Field(default=None, ge=1, le=M0407_MAX_ANALYSIS_TARGETS)
    analysis_retain_target_count: int | None = Field(
        default=None, ge=0, le=M0407_MAX_ANALYSIS_TARGETS
    )
    analysis_review_target_count: int | None = Field(
        default=None, ge=0, le=M0407_MAX_ANALYSIS_TARGETS
    )
    analysis_exclude_target_count: int | None = Field(
        default=None, ge=0, le=M0407_MAX_ANALYSIS_TARGETS
    )
    analysis_evaluable_target_count: int | None = Field(
        default=None, ge=0, le=M0407_MAX_ANALYSIS_TARGETS
    )
    analysis_digest: Sha256Digest | None = None
    receipt_digest: Sha256Digest

    @field_validator("analysis_platform_level_ids")
    @classmethod
    def platform_ids_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if any(re.fullmatch(r"level\.[0-9a-f]{64}", value) is None for value in values):
            raise ValueError("platform level identifiers must preserve M04-06 opaque aliases")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def receipt_shape_is_closed(self) -> ProteoformHarmonizationSupportReceipt:
        from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
            harmonization_support_receipt_digest,
        )

        if len(self.analysis_platform_level_ids) != len(set(self.analysis_platform_level_ids)):
            raise ValueError("harmonization platform identifiers must be unique")
        expected_artifact_id = f"result.m0406.{self.request_digest.removeprefix('sha256:')}"
        if (
            self.artifact_reference.artifact_id != expected_artifact_id
            or self.artifact_reference.version != M0407_CONTRACT_VERSION
            or self.artifact_reference.media_type != _M0406_RESULT_MEDIA_TYPE
            or self.artifact_reference.digest != self.result_digest
        ):
            raise ValueError("harmonization receipt artifact does not bind the exact M04-06 result")
        counts = (
            self.analysis_target_count,
            self.analysis_retain_target_count,
            self.analysis_review_target_count,
            self.analysis_exclude_target_count,
            self.analysis_evaluable_target_count,
        )
        if self.disposition is ProteoformHarmonizationDisposition.ACCEPTED:
            if (
                any(value is None for value in counts)
                or self.applicability is None
                or self.analysis_digest is None
                or not self.analysis_platform_level_ids
            ):
                raise ValueError(
                    "accepted harmonization receipt requires its successful projection"
                )
            total, retained, review, excluded, evaluable = counts
            if (
                total is None
                or retained is None
                or review is None
                or excluded is None
                or evaluable is None
                or retained + review + excluded != total
                or evaluable > retained
            ):
                raise ValueError("harmonization support counts do not form a closed partition")
            if self.support_status is not SupportStatus.LIMITED or self.human_review_required:
                raise ValueError("accepted harmonization receipt has an invalid support envelope")
        elif (
            any(value is not None for value in counts)
            or self.analysis_platform_level_ids
            or self.analysis_digest is not None
        ):
            raise ValueError("non-accepted harmonization receipt cannot project analysis values")
        expected_status = {
            ProteoformHarmonizationDisposition.ACCEPTED: SupportStatus.LIMITED,
            ProteoformHarmonizationDisposition.QUARANTINED: SupportStatus.REVIEW_REQUIRED,
            ProteoformHarmonizationDisposition.ABSTAINED: SupportStatus.UNSUPPORTED,
        }[self.disposition]
        if self.support_status is not expected_status or self.human_review_required is not (
            self.disposition is not ProteoformHarmonizationDisposition.ACCEPTED
        ):
            raise ValueError("harmonization receipt disposition and support envelope contradict")
        if self.receipt_digest != harmonization_support_receipt_digest(self):
            raise ValueError("harmonization support receipt digest does not match its content")
        return self


class ProteoformSupportPrerequisites(FrozenModel):
    quality_result: ProteoformQualityResult
    harmonization_result: ProteoformHarmonizationResult
    quality: ProteoformQualitySupportReceipt
    harmonization: ProteoformHarmonizationSupportReceipt

    @field_validator("quality_result", mode="before")
    @classmethod
    def quality_result_is_fully_replayed(cls, value: object) -> ProteoformQualityResult:
        return ProteoformQualityResult.model_validate_json(canonical_json_bytes(value), strict=True)

    @field_validator("harmonization_result", mode="before")
    @classmethod
    def harmonization_result_is_fully_replayed(cls, value: object) -> ProteoformHarmonizationResult:
        return ProteoformHarmonizationResult.model_validate_json(
            canonical_json_bytes(value), strict=True
        )

    @model_validator(mode="after")
    def chain_is_closed(self) -> ProteoformSupportPrerequisites:
        if self.quality != quality_support_receipt(self.quality_result):
            raise ValueError(
                "quality receipt is not the exact projection of its full M04-04 result"
            )
        if self.harmonization != harmonization_support_receipt(self.harmonization_result):
            raise ValueError(
                "harmonization receipt is not the exact projection of its full M04-06 result"
            )
        if (
            self.harmonization_result.request.artifact_result.request.quality_result
            != self.quality_result
        ):
            raise ValueError("M04-06 does not embed the exact supplied M04-04 result")
        if self.quality.result_digest != self.harmonization.quality_result_digest:
            raise ValueError("harmonization receipt does not bind the exact quality result")
        if self.quality.identity_resolution_digest != self.harmonization.identity_resolution_digest:
            raise ValueError("support prerequisites disagree on identity lineage")
        if self.quality.completed_at > self.harmonization.completed_at:
            raise ValueError("support prerequisite chronology is impossible")
        if (
            self.quality.disposition is ProteoformQualityDisposition.QUALIFIED
            and self.harmonization.disposition is ProteoformHarmonizationDisposition.ACCEPTED
        ) and (
            self.quality.applicability != self.harmonization.applicability
            or self.quality.assay_protocol_version != self.harmonization.assay_protocol_version
            or self.quality.specimen_processing_version
            != self.harmonization.specimen_processing_version
            or self.quality.controlled_vocabulary_id != self.harmonization.controlled_vocabulary_id
            or self.quality.controlled_vocabulary_version
            != self.harmonization.controlled_vocabulary_version
            or self.quality.unit_system_version != self.harmonization.unit_system_version
        ):
            raise ValueError("support prerequisites disagree on applicability or protocol versions")
        return self


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _ReplayedM0407PrerequisitesCapability:
    seal: object
    prerequisites: ProteoformSupportPrerequisites
    quality_result: ProteoformQualityResult
    harmonization_result: ProteoformHarmonizationResult
    normalized_snapshot_digest: Sha256Digest


@dataclass(frozen=True, slots=True)
class _ExpectedSupportRouteBundle:
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    envelope_assessments: tuple[ProteoformEnvelopeAssessment, ...]
    matched_envelope_ids: tuple[Identifier, ...]
    abstention_reasons: tuple[ProteoformAbstention, ...]
    disposition: ProteoformSupportDisposition
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...]
    limitations: tuple[Limitation, ...]


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _ValidatedM0407RequestCapability:
    seal: object
    request: RouteProteoformSupportRequest
    request_digest: Sha256Digest
    request_snapshot_digest: Sha256Digest
    prerequisites: ProteoformSupportPrerequisites
    quality_result: ProteoformQualityResult
    harmonization_result: ProteoformHarmonizationResult
    bundle: _ExpectedSupportRouteBundle
    bundle_snapshot_digest: Sha256Digest
    expected_result_digest: Sha256Digest


_ISSUED_PREREQUISITES_CAPABILITIES: Final[
    WeakKeyDictionary[
        _ReplayedM0407PrerequisitesCapability,
        tuple[
            ProteoformSupportPrerequisites,
            ProteoformQualityResult,
            ProteoformHarmonizationResult,
            Sha256Digest,
        ],
    ]
] = WeakKeyDictionary()
_ISSUED_REQUEST_CAPABILITIES: Final[
    WeakKeyDictionary[
        _ValidatedM0407RequestCapability,
        tuple[
            RouteProteoformSupportRequest,
            Sha256Digest,
            Sha256Digest,
            ProteoformSupportPrerequisites,
            ProteoformQualityResult,
            ProteoformHarmonizationResult,
            _ExpectedSupportRouteBundle,
            Sha256Digest,
            Sha256Digest,
        ],
    ]
] = WeakKeyDictionary()


def _exact_prerequisites_capability(
    value: object,
) -> _ReplayedM0407PrerequisitesCapability | None:
    return value if type(value) is _ReplayedM0407PrerequisitesCapability else None


def _exact_request_capability(value: object) -> _ValidatedM0407RequestCapability | None:
    return value if type(value) is _ValidatedM0407RequestCapability else None


def _support_route_bundle_snapshot_digest(
    bundle: _ExpectedSupportRouteBundle,
) -> Sha256Digest:
    return sha256_digest(
        {
            "request_digest": bundle.request_digest,
            "profile_digest": bundle.profile_digest,
            "policy_digest": bundle.policy_digest,
            "configuration_digest": bundle.configuration_digest,
            "envelope_assessments": bundle.envelope_assessments,
            "matched_envelope_ids": bundle.matched_envelope_ids,
            "abstention_reasons": bundle.abstention_reasons,
            "disposition": bundle.disposition,
            "support": bundle.support,
            "uncertainty": bundle.uncertainty,
            "provenance": bundle.provenance,
            "evidence": bundle.evidence,
            "limitations": bundle.limitations,
        }
    )


def _support_route_bundle_members_are_exact(bundle: _ExpectedSupportRouteBundle) -> bool:
    return (
        type(bundle) is _ExpectedSupportRouteBundle
        and type(bundle.request_digest) is str
        and type(bundle.profile_digest) is str
        and type(bundle.policy_digest) is str
        and type(bundle.configuration_digest) is str
        and type(bundle.envelope_assessments) is tuple
        and all(type(item) is ProteoformEnvelopeAssessment for item in bundle.envelope_assessments)
        and type(bundle.matched_envelope_ids) is tuple
        and all(type(item) is str for item in bundle.matched_envelope_ids)
        and type(bundle.abstention_reasons) is tuple
        and all(type(item) is ProteoformAbstention for item in bundle.abstention_reasons)
        and type(bundle.disposition) is ProteoformSupportDisposition
        and type(bundle.support) is SupportDecision
        and type(bundle.uncertainty) is UncertaintyProfile
        and type(bundle.provenance) is ProvenanceRecord
        and type(bundle.evidence) is tuple
        and all(type(item) is EvidenceReference for item in bundle.evidence)
        and type(bundle.limitations) is tuple
        and all(type(item) is Limitation for item in bundle.limitations)
    )


def _prerequisites_capability_is_issued(
    capability: _ReplayedM0407PrerequisitesCapability,
) -> bool:
    if type(capability) is not _ReplayedM0407PrerequisitesCapability:
        return False
    try:
        prerequisites = capability.prerequisites
        quality_result = capability.quality_result
        harmonization_result = capability.harmonization_result
        snapshot_digest = capability.normalized_snapshot_digest
        if (
            capability.seal is not _VALIDATION_CAPABILITY_SEAL
            or type(prerequisites) is not ProteoformSupportPrerequisites
            or type(quality_result) is not ProteoformQualityResult
            or type(harmonization_result) is not ProteoformHarmonizationResult
            or type(snapshot_digest) is not str
        ):
            return False
        prerequisite_quality = prerequisites.quality_result
        prerequisite_harmonization = prerequisites.harmonization_result
        if (
            type(prerequisite_quality) is not ProteoformQualityResult
            or type(prerequisite_harmonization) is not ProteoformHarmonizationResult
        ):
            return False
        with _VALIDATION_CAPABILITY_LOCK:
            snapshot = _ISSUED_PREREQUISITES_CAPABILITIES.get(capability)
        if (
            snapshot is None
            or type(snapshot) is not tuple
            or len(snapshot) != _PREREQUISITES_CAPABILITY_SNAPSHOT_LENGTH
            or type(snapshot[0]) is not ProteoformSupportPrerequisites
            or type(snapshot[1]) is not ProteoformQualityResult
            or type(snapshot[2]) is not ProteoformHarmonizationResult
            or type(snapshot[3]) is not str
        ):
            return False
        return (
            snapshot[0] is prerequisites
            and snapshot[1] is quality_result
            and snapshot[2] is harmonization_result
            and snapshot[3] == snapshot_digest
            and prerequisite_quality is quality_result
            and prerequisite_harmonization is harmonization_result
            and sha256_digest(prerequisites) == snapshot_digest
        )
    except Exception:  # noqa: BLE001 - corrupted private capabilities fail closed.
        return False


def _request_capability_is_issued(capability: _ValidatedM0407RequestCapability) -> bool:
    from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
        canonical_request_digest,
    )

    if type(capability) is not _ValidatedM0407RequestCapability:
        return False
    try:
        request = capability.request
        request_digest = capability.request_digest
        request_snapshot_digest = capability.request_snapshot_digest
        prerequisites = capability.prerequisites
        quality_result = capability.quality_result
        harmonization_result = capability.harmonization_result
        bundle = capability.bundle
        bundle_snapshot_digest = capability.bundle_snapshot_digest
        expected_result_digest = capability.expected_result_digest
        if (
            capability.seal is not _VALIDATION_CAPABILITY_SEAL
            or type(request) is not RouteProteoformSupportRequest
            or type(request_digest) is not str
            or type(request_snapshot_digest) is not str
            or type(prerequisites) is not ProteoformSupportPrerequisites
            or type(quality_result) is not ProteoformQualityResult
            or type(harmonization_result) is not ProteoformHarmonizationResult
            or not _support_route_bundle_members_are_exact(bundle)
            or type(bundle_snapshot_digest) is not str
            or type(expected_result_digest) is not str
        ):
            return False
        request_prerequisites = request.prerequisites
        prerequisite_quality = prerequisites.quality_result
        prerequisite_harmonization = prerequisites.harmonization_result
        if (
            type(request_prerequisites) is not ProteoformSupportPrerequisites
            or type(prerequisite_quality) is not ProteoformQualityResult
            or type(prerequisite_harmonization) is not ProteoformHarmonizationResult
        ):
            return False
        with _VALIDATION_CAPABILITY_LOCK:
            snapshot = _ISSUED_REQUEST_CAPABILITIES.get(capability)
        if (
            snapshot is None
            or type(snapshot) is not tuple
            or len(snapshot) != _REQUEST_CAPABILITY_SNAPSHOT_LENGTH
            or type(snapshot[0]) is not RouteProteoformSupportRequest
            or type(snapshot[1]) is not str
            or type(snapshot[2]) is not str
            or type(snapshot[3]) is not ProteoformSupportPrerequisites
            or type(snapshot[4]) is not ProteoformQualityResult
            or type(snapshot[5]) is not ProteoformHarmonizationResult
            or type(snapshot[6]) is not _ExpectedSupportRouteBundle
            or type(snapshot[7]) is not str
            or type(snapshot[8]) is not str
        ):
            return False
        return (
            snapshot[0] is request
            and snapshot[1] == request_digest
            and snapshot[2] == request_snapshot_digest
            and snapshot[3] is prerequisites
            and snapshot[4] is quality_result
            and snapshot[5] is harmonization_result
            and snapshot[6] is bundle
            and snapshot[7] == bundle_snapshot_digest
            and snapshot[8] == expected_result_digest
            and request_prerequisites is prerequisites
            and prerequisite_quality is quality_result
            and prerequisite_harmonization is harmonization_result
            and canonical_request_digest(request) == request_digest
            and sha256_digest(request) == request_snapshot_digest
            and _support_route_bundle_snapshot_digest(bundle) == bundle_snapshot_digest
        )
    except Exception:  # noqa: BLE001 - corrupted private capabilities fail closed.
        return False


def _issue_prerequisites_replay_capability(
    prerequisites: ProteoformSupportPrerequisites,
) -> _ReplayedM0407PrerequisitesCapability:
    if type(prerequisites) is not ProteoformSupportPrerequisites:
        raise TypeError("M04-07 prerequisite capability requires exact prerequisites")
    quality_result = prerequisites.quality_result
    harmonization_result = prerequisites.harmonization_result
    if (
        type(quality_result) is not ProteoformQualityResult
        or type(harmonization_result) is not ProteoformHarmonizationResult
    ):
        raise TypeError("M04-07 prerequisite capability requires exact upstream results")
    snapshot_digest = sha256_digest(prerequisites)
    capability = _ReplayedM0407PrerequisitesCapability(
        seal=_VALIDATION_CAPABILITY_SEAL,
        prerequisites=prerequisites,
        quality_result=quality_result,
        harmonization_result=harmonization_result,
        normalized_snapshot_digest=snapshot_digest,
    )
    with _VALIDATION_CAPABILITY_LOCK:
        _ISSUED_PREREQUISITES_CAPABILITIES[capability] = (
            prerequisites,
            quality_result,
            harmonization_result,
            snapshot_digest,
        )
    return capability


def _issue_validated_request_capability(
    request: RouteProteoformSupportRequest,
    bundle: _ExpectedSupportRouteBundle,
    expected_result_digest: Sha256Digest,
) -> _ValidatedM0407RequestCapability:
    if (
        type(request) is not RouteProteoformSupportRequest
        or not _support_route_bundle_members_are_exact(bundle)
        or type(expected_result_digest) is not str
    ):
        raise TypeError("M04-07 result capability requires exact validated inputs")
    prerequisites = request.prerequisites
    if type(prerequisites) is not ProteoformSupportPrerequisites:
        raise TypeError("M04-07 result capability requires exact prerequisites")
    quality_result = prerequisites.quality_result
    harmonization_result = prerequisites.harmonization_result
    if (
        type(quality_result) is not ProteoformQualityResult
        or type(harmonization_result) is not ProteoformHarmonizationResult
    ):
        raise TypeError("M04-07 result capability requires exact upstream results")
    request_snapshot_digest = sha256_digest(request)
    bundle_snapshot_digest = _support_route_bundle_snapshot_digest(bundle)
    capability = _ValidatedM0407RequestCapability(
        seal=_VALIDATION_CAPABILITY_SEAL,
        request=request,
        request_digest=bundle.request_digest,
        request_snapshot_digest=request_snapshot_digest,
        prerequisites=prerequisites,
        quality_result=quality_result,
        harmonization_result=harmonization_result,
        bundle=bundle,
        bundle_snapshot_digest=bundle_snapshot_digest,
        expected_result_digest=expected_result_digest,
    )
    with _VALIDATION_CAPABILITY_LOCK:
        _ISSUED_REQUEST_CAPABILITIES[capability] = (
            request,
            bundle.request_digest,
            request_snapshot_digest,
            prerequisites,
            quality_result,
            harmonization_result,
            bundle,
            bundle_snapshot_digest,
            expected_result_digest,
        )
    return capability


def _validate_request_with_prerequisites_capability(
    value: object,
    capability: _ReplayedM0407PrerequisitesCapability,
) -> RouteProteoformSupportRequest:
    """Validate after one full prerequisite admission using its issued snapshot."""

    if not _prerequisites_capability_is_issued(capability):
        raise TypeError("invalid M04-07 prerequisite replay capability")
    return RouteProteoformSupportRequest.model_validate(
        value,
        strict=True,
        context={
            _PREREQUISITES_CAPABILITY_CONTEXT_KEY: capability,
            _PREREQUISITES_CAPABILITY_VERIFIED_KEY: capability,
        },
    )


def _validate_result_with_capability(
    value: object,
    capability: _ValidatedM0407RequestCapability,
) -> ProteoformSupportRouteResult:
    """Validate one owned result against its issued request and derived bundle."""

    if not _request_capability_is_issued(capability):
        raise TypeError("invalid M04-07 request-validation capability")
    return ProteoformSupportRouteResult.model_validate(
        value,
        strict=True,
        context={
            _REQUEST_CAPABILITY_CONTEXT_KEY: capability,
            _REQUEST_CAPABILITY_VERIFIED_KEY: capability,
        },
    )


class ProteoformDeclaredSupportFact(FrozenModel):
    dimension: Literal[
        ProteoformSupportDimension.SPECIMEN,
        ProteoformSupportDimension.DISEASE_CLASS,
        ProteoformSupportDimension.REFERENCE,
        ProteoformSupportDimension.INTENDED_USE,
    ]
    state: ProteoformDeclaredSupportState
    values: tuple[Identifier, ...] = Field(default=(), max_length=M0407_MAX_FACT_VALUES)
    evidence: tuple[ArtifactReference, ...] = Field(
        default=(), max_length=M0407_MAX_EVIDENCE_PER_FACT
    )

    @field_validator("values")
    @classmethod
    def values_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        return tuple(sorted(values))

    @field_validator("evidence")
    @classmethod
    def evidence_is_canonical(
        cls, values: tuple[ArtifactReference, ...]
    ) -> tuple[ArtifactReference, ...]:
        for value in values:
            _owned_evidence(value)
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def declaration_is_closed(self) -> ProteoformDeclaredSupportFact:
        if len(self.values) != len(set(self.values)) or len(self.evidence) != len(
            set(self.evidence)
        ):
            raise ValueError("declared support fact collections must be unique")
        namespace = {
            ProteoformSupportDimension.SPECIMEN: "specimen",
            ProteoformSupportDimension.DISEASE_CLASS: "disease",
            ProteoformSupportDimension.REFERENCE: "reference",
            ProteoformSupportDimension.INTENDED_USE: "use",
        }[self.dimension]
        for value in self.values:
            opaque_support_identifier(namespace, value)
        if self.state is ProteoformDeclaredSupportState.OBSERVED:
            if not self.values or not self.evidence:
                raise ValueError("observed support fact requires values and evidence")
        elif self.values or self.evidence:
            raise ValueError("missing or unknown support fact cannot carry values or evidence")
        return self


class ProteoformContextReceipt(FrozenModel):
    role: ProteoformContextRole
    state: ProteoformDeclaredSupportState
    reference: ArtifactReference | None = None

    @model_validator(mode="after")
    def context_shape_is_closed(self) -> ProteoformContextReceipt:
        if self.state is ProteoformDeclaredSupportState.OBSERVED:
            if self.reference is None:
                raise ValueError("observed context receipt requires evidence")
            _owned_evidence(self.reference)
        elif self.reference is not None:
            raise ValueError("missing or unknown context receipt cannot carry evidence")
        return self


class ProteoformDimensionRemediation(FrozenModel):
    dimension: ProteoformSupportDimension
    outside_reason_code: Identifier
    indeterminate_reason_code: Identifier
    remediation_code: Identifier
    remediation_path: ProteoformRemediationPath

    @field_validator("outside_reason_code", "indeterminate_reason_code")
    @classmethod
    def reason_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("reason", value)

    @field_validator("remediation_code")
    @classmethod
    def remediation_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("remediation", value)


class ProteoformSupportEnvelope(FrozenModel):
    envelope_id: Identifier
    applicabilities: tuple[ProteoformApplicability, ...] = Field(min_length=1, max_length=4)
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0407_MAX_APPROVED_VERSIONS
    )
    approved_specimen_processing_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0407_MAX_APPROVED_VERSIONS
    )
    approved_controlled_vocabulary_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0407_MAX_APPROVED_VERSIONS
    )
    approved_controlled_vocabulary_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0407_MAX_APPROVED_VERSIONS
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0407_MAX_APPROVED_VERSIONS
    )
    specimen_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=M0407_MAX_FACT_VALUES)
    disease_class_terms: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0407_MAX_FACT_VALUES
    )
    quality_statuses: tuple[ProteoformQualityMetricStatus, ...] = Field(min_length=1, max_length=5)
    minimum_completeness_ppm: int = Field(ge=0, le=M0407_RATE_SCALE)
    platform_level_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0407_MAX_PLATFORM_LEVEL_IDS
    )
    reference_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=M0407_MAX_FACT_VALUES)
    intended_use_terms: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0407_MAX_FACT_VALUES
    )
    required_context_roles: tuple[ProteoformContextRole, ...] = Field(
        min_length=1, max_length=M0407_CONTEXT_RECEIPT_COUNT
    )
    remediations: tuple[ProteoformDimensionRemediation, ...] = Field(
        min_length=M0407_DIMENSION_COUNT, max_length=M0407_DIMENSION_COUNT
    )

    @field_validator("envelope_id")
    @classmethod
    def envelope_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("envelope", value)

    @field_validator(
        "applicabilities",
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabulary_ids",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
        "specimen_terms",
        "disease_class_terms",
        "quality_statuses",
        "platform_level_ids",
        "reference_terms",
        "intended_use_terms",
        "required_context_roles",
    )
    @classmethod
    def semantic_sets_are_canonical(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        if len(values) != len(set(values)):
            raise ValueError("support envelope collections must be unique")
        return tuple(sorted(values))

    @field_validator("remediations")
    @classmethod
    def remediations_are_canonical(
        cls, values: tuple[ProteoformDimensionRemediation, ...]
    ) -> tuple[ProteoformDimensionRemediation, ...]:
        return tuple(sorted(values, key=lambda item: item.dimension.value))

    @model_validator(mode="after")
    def envelope_is_relationally_closed(self) -> ProteoformSupportEnvelope:
        if {item.dimension for item in self.remediations} != set(ProteoformSupportDimension):
            raise ValueError("support envelope requires one remediation per dimension")
        namespaces = (
            (self.specimen_terms, "specimen"),
            (self.disease_class_terms, "disease"),
            (self.platform_level_ids, "level"),
            (self.reference_terms, "reference"),
            (self.intended_use_terms, "use"),
        )
        for values, namespace in namespaces:
            for value in values:
                if namespace == "level":
                    if re.fullmatch(r"level\.[0-9a-f]{64}", value) is None:
                        raise ValueError("platform values must preserve M04-06 level aliases")
                else:
                    opaque_support_identifier(namespace, value)
        return self


class ProteoformSupportProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    envelopes: tuple[ProteoformSupportEnvelope, ...] = Field(
        min_length=1, max_length=M0407_MAX_ENVELOPES
    )
    evidence: ArtifactReference

    @field_validator("profile_id")
    @classmethod
    def profile_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("profile", value)

    @field_validator("envelopes")
    @classmethod
    def envelopes_are_canonical(
        cls, values: tuple[ProteoformSupportEnvelope, ...]
    ) -> tuple[ProteoformSupportEnvelope, ...]:
        if len({item.envelope_id for item in values}) != len(values):
            raise ValueError("support profile envelope identifiers must be unique")
        return tuple(sorted(values, key=lambda item: item.envelope_id))

    @field_validator("evidence")
    @classmethod
    def profile_evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)


class ProteoformSupportPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_envelopes: int = Field(gt=0, le=M0407_MAX_ENVELOPES)
    require_releasable_prerequisites: Literal[True] = True
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("policy_id")
    @classmethod
    def policy_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("policy", value)

    @field_validator("reviewed_by")
    @classmethod
    def reviewer_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("reviewer", value)

    @field_validator("evidence")
    @classmethod
    def policy_evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)


class RouteProteoformSupportRequest(FrozenModel):
    operation: Literal["route_proteoform_support"] = M0407_OPERATION
    contract_version: Literal["1.0.0"] = M0407_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    prerequisites: ProteoformSupportPrerequisites
    profile: ProteoformSupportProfile
    policy: ProteoformSupportPolicy
    declared_facts: tuple[ProteoformDeclaredSupportFact, ...] = Field(
        min_length=M0407_DECLARED_FACT_COUNT, max_length=M0407_DECLARED_FACT_COUNT
    )
    context_receipts: tuple[ProteoformContextReceipt, ...] = Field(
        min_length=M0407_CONTEXT_RECEIPT_COUNT, max_length=M0407_CONTEXT_RECEIPT_COUNT
    )
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("prerequisites", mode="wrap")
    @classmethod
    def prerequisites_are_fully_replayed(
        cls,
        value: object,
        _handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> ProteoformSupportPrerequisites:
        context = info.context if type(info.context) is dict else None
        capability: object = (
            context.get(_PREREQUISITES_CAPABILITY_CONTEXT_KEY) if context is not None else None
        )
        typed_capability = _exact_prerequisites_capability(capability)
        verified = (
            context is not None
            and context.get(_PREREQUISITES_CAPABILITY_VERIFIED_KEY) is typed_capability
        )
        if (
            typed_capability is not None
            and typed_capability.seal is _VALIDATION_CAPABILITY_SEAL
            and (verified or _prerequisites_capability_is_issued(typed_capability))
            and value is typed_capability.prerequisites
        ):
            if context is not None:
                context[_PREREQUISITES_CAPABILITY_VERIFIED_KEY] = typed_capability
            return typed_capability.prerequisites
        return ProteoformSupportPrerequisites.model_validate_json(
            canonical_json_bytes(value), strict=True
        )

    @field_validator("request_id")
    @classmethod
    def request_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("request", value)

    @field_validator("declared_facts")
    @classmethod
    def facts_are_canonical(
        cls, values: tuple[ProteoformDeclaredSupportFact, ...]
    ) -> tuple[ProteoformDeclaredSupportFact, ...]:
        return tuple(sorted(values, key=lambda item: item.dimension.value))

    @field_validator("context_receipts")
    @classmethod
    def contexts_are_canonical(
        cls, values: tuple[ProteoformContextReceipt, ...]
    ) -> tuple[ProteoformContextReceipt, ...]:
        return tuple(sorted(values, key=lambda item: item.role.value))

    @model_validator(mode="after")
    def request_is_authorized_bound_and_closed(self) -> RouteProteoformSupportRequest:
        _validate_route_boundary(self)
        if len(canonical_json_bytes(self)) > M0407_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("M04-07 canonical request exceeds the public ingress byte limit")
        return self


class ProteoformDimensionAssessment(FrozenModel):
    dimension: ProteoformSupportDimension
    decision: ProteoformDimensionSupportDecision
    values: tuple[Identifier, ...] = Field(default=(), max_length=M0407_MAX_FACT_VALUES)
    numeric_value_ppm: int | None = Field(default=None, ge=0, le=M0407_RATE_SCALE)
    reason_code: Identifier | None = None
    remediation_code: Identifier | None = None
    remediation_path: ProteoformRemediationPath | None = None

    @field_validator("values")
    @classmethod
    def values_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("dimension assessment values must be unique")
        return tuple(sorted(values))

    @field_validator("reason_code")
    @classmethod
    def reason_is_opaque(cls, value: Identifier | None) -> Identifier | None:
        return None if value is None else opaque_support_identifier("reason", value)

    @field_validator("remediation_code")
    @classmethod
    def remediation_is_opaque(cls, value: Identifier | None) -> Identifier | None:
        return None if value is None else opaque_support_identifier("remediation", value)

    @model_validator(mode="after")
    def codes_match_decision(self) -> ProteoformDimensionAssessment:
        remediation = (self.reason_code, self.remediation_code, self.remediation_path)
        has_any = any(value is not None for value in remediation)
        has_all = all(value is not None for value in remediation)
        if self.decision is ProteoformDimensionSupportDecision.SUPPORTED:
            if has_any:
                raise ValueError("supported dimension assessments cannot carry remediation")
        elif not has_all:
            raise ValueError("only blocking dimension assessments require remediation")
        return self


class ProteoformEnvelopeAssessment(FrozenModel):
    envelope_id: Identifier
    decision: ProteoformEnvelopeSupportDecision
    dimensions: tuple[ProteoformDimensionAssessment, ...] = Field(
        min_length=M0407_DIMENSION_COUNT, max_length=M0407_DIMENSION_COUNT
    )

    @field_validator("envelope_id")
    @classmethod
    def envelope_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("envelope", value)

    @field_validator("dimensions")
    @classmethod
    def dimensions_are_canonical(
        cls, values: tuple[ProteoformDimensionAssessment, ...]
    ) -> tuple[ProteoformDimensionAssessment, ...]:
        return tuple(sorted(values, key=lambda item: item.dimension.value))

    @model_validator(mode="after")
    def decision_matches_dimensions(self) -> ProteoformEnvelopeAssessment:
        if {item.dimension for item in self.dimensions} != set(ProteoformSupportDimension):
            raise ValueError("envelope assessment must cover all eight dimensions")
        decisions = {item.decision for item in self.dimensions}
        expected = (
            ProteoformEnvelopeSupportDecision.ELIMINATED
            if ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN in decisions
            else ProteoformEnvelopeSupportDecision.PROVISIONAL
            if ProteoformDimensionSupportDecision.INDETERMINATE in decisions
            else ProteoformEnvelopeSupportDecision.CONFIRMED
        )
        if self.decision is not expected:
            raise ValueError("envelope decision contradicts dimension assessments")
        return self


class ProteoformAbstention(FrozenModel):
    code: ProteoformAbstentionCode
    envelope_id: Identifier | None = None
    dimension: ProteoformSupportDimension | None = None
    upstream_module_id: Literal["GLIO-PROTEOGEN-M04-04", "GLIO-PROTEOGEN-M04-06"] | None = None
    reason_code: Identifier
    remediation_code: Identifier
    remediation_path: ProteoformRemediationPath

    @field_validator("envelope_id")
    @classmethod
    def envelope_is_opaque(cls, value: Identifier | None) -> Identifier | None:
        return None if value is None else opaque_support_identifier("envelope", value)

    @field_validator("reason_code")
    @classmethod
    def reason_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("reason", value)

    @field_validator("remediation_code")
    @classmethod
    def remediation_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("remediation", value)

    @model_validator(mode="after")
    def shape_matches_code(self) -> ProteoformAbstention:
        if self.code in {
            ProteoformAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
            ProteoformAbstentionCode.DIMENSION_INDETERMINATE,
        }:
            if self.envelope_id is None or self.dimension is None or self.upstream_module_id:
                raise ValueError("dimension abstention requires only envelope and dimension")
        elif self.code is ProteoformAbstentionCode.PREREQUISITE_UNRELEASABLE:
            if self.upstream_module_id is None or self.envelope_id or self.dimension:
                raise ValueError("prerequisite abstention requires only its upstream module")
        elif self.envelope_id or self.dimension or self.upstream_module_id:
            raise ValueError("joint-combination abstention cannot name one dimension")
        return self


class ProteoformSupportRouteResult(FrozenModel):
    output_type: Literal["proteoform_support_route_result"] = "proteoform_support_route_result"
    route_id: Identifier
    result_version: Literal["1.0.0"] = M0407_CONTRACT_VERSION
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RouteProteoformSupportRequest
    disposition: ProteoformSupportDisposition
    matched_envelope_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0407_MAX_ENVELOPES)
    envelope_assessments: tuple[ProteoformEnvelopeAssessment, ...] = Field(
        min_length=1, max_length=M0407_MAX_ENVELOPES
    )
    abstention_reasons: tuple[ProteoformAbstention, ...] = Field(
        default=(), max_length=M0407_MAX_ABSTENTIONS
    )
    parent_target: Literal["protein_rna_discordance"] = M0407_PARENT
    emits_protein_rna_discordance: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    localizes_modification: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_cn_to_protein_regression: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    executes_model: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0407_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("request", mode="wrap")
    @classmethod
    def request_is_fully_replayed(
        cls,
        value: object,
        _handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> RouteProteoformSupportRequest:
        context = info.context if type(info.context) is dict else None
        capability: object = (
            context.get(_REQUEST_CAPABILITY_CONTEXT_KEY) if context is not None else None
        )
        typed_capability = _exact_request_capability(capability)
        verified = (
            context is not None
            and context.get(_REQUEST_CAPABILITY_VERIFIED_KEY) is typed_capability
        )
        if (
            typed_capability is not None
            and typed_capability.seal is _VALIDATION_CAPABILITY_SEAL
            and (verified or _request_capability_is_issued(typed_capability))
            and value is typed_capability.request
        ):
            if context is not None:
                context[_REQUEST_CAPABILITY_VERIFIED_KEY] = typed_capability
            return typed_capability.request
        return RouteProteoformSupportRequest.model_validate_json(
            canonical_json_bytes(value), strict=True
        )

    @field_validator("route_id")
    @classmethod
    def route_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("route", value)

    @field_validator("matched_envelope_ids")
    @classmethod
    def matches_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("matched support envelopes must be unique")
        return tuple(sorted(values))

    @field_validator("envelope_assessments", "abstention_reasons", "evidence", "limitations")
    @classmethod
    def result_collections_are_canonical(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

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
            }
        )

    @model_validator(mode="after")
    def result_is_relationally_closed(
        self,
        info: ValidationInfo,
    ) -> ProteoformSupportRouteResult:
        context = info.context if type(info.context) is dict else None
        capability: object = (
            context.get(_REQUEST_CAPABILITY_CONTEXT_KEY) if context is not None else None
        )
        typed_capability = _exact_request_capability(capability)
        sealed_capability: _ValidatedM0407RequestCapability | None = None
        if typed_capability is not None:
            capability_request = typed_capability.request
            is_verified = (
                typed_capability.seal is _VALIDATION_CAPABILITY_SEAL
                and context is not None
                and context.get(_REQUEST_CAPABILITY_VERIFIED_KEY) is typed_capability
                and self.request is capability_request
            )
            if is_verified:
                sealed_capability = typed_capability
        bundle = (
            sealed_capability.bundle
            if sealed_capability is not None
            else _expected_support_route_bundle(self.request)
        )
        _validate_result(self, bundle)
        from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
            result_payload_digest,
        )

        expected = (
            sealed_capability.expected_result_digest
            if sealed_capability is not None
            else result_payload_digest(self)
        )
        if self.result_digest != expected:
            raise ValueError("M04-07 result digest does not match its content")
        return self


def _opaque(namespace: str, value: object) -> Identifier:
    return f"{namespace}.{sha256_digest(value).removeprefix('sha256:')}"


def quality_support_receipt(value: object) -> ProteoformQualitySupportReceipt:
    """Project a strict full M04-04 result to its privacy-minimized support receipt."""

    result = ProteoformQualityResult.model_validate_json(canonical_json_bytes(value), strict=True)
    qualified = result.disposition is ProteoformQualityDisposition.QUALIFIED
    lineage_result = result.request.raw_input_result.request.lineage_result
    protocol_result = lineage_result.request.protocol_result
    protocol = protocol_result.request.protocol_schema
    metrics = (
        tuple(
            ProteoformQualityMetricSupportReceipt(
                role=item.role,
                metric_code=item.metric_code,
                observation_state=item.observation_state,
                status=item.status,
                value_ppm=item.value_ppm,
            )
            for assay in result.assay_quality
            for item in assay.metrics
        )
        if qualified
        else ()
    )
    payload: dict[str, object] = {
        "module_id": "GLIO-PROTEOGEN-M04-04",
        "receipt_version": M0407_CONTRACT_VERSION,
        "artifact_reference": ArtifactReference(
            artifact_id=f"result.m0404.{result.request_digest.removeprefix('sha256:')}",
            version=M0407_CONTRACT_VERSION,
            digest=result.result_digest,
            media_type=_M0404_RESULT_MEDIA_TYPE,
        ),
        "result_digest": result.result_digest,
        "request_digest": result.request_digest,
        "policy_digest": result.policy_digest,
        "configuration_digest": result.configuration_digest,
        "disposition": result.disposition,
        "support_status": result.support.status,
        "human_review_required": result.human_review_required,
        "completed_at": result.completed_at,
        "identity_resolution_digest": result.receipt.identity_resolution_digest,
        "applicability": protocol.applicability if qualified else None,
        "assay_protocol_version": protocol.assay_protocol_version,
        "specimen_processing_version": protocol.specimen_processing_version,
        "controlled_vocabulary_id": protocol.controlled_vocabulary_id,
        "controlled_vocabulary_version": protocol.controlled_vocabulary_version,
        "unit_system_version": protocol.unit_system_version,
        "metrics": metrics,
    }
    from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
        quality_support_receipt_digest,
    )

    payload["receipt_digest"] = quality_support_receipt_digest(payload)
    return ProteoformQualitySupportReceipt.model_validate(payload, strict=True)


def harmonization_support_receipt(
    value: object,
) -> ProteoformHarmonizationSupportReceipt:
    """Project a strict full M04-06 result to its privacy-minimized support receipt."""

    result = ProteoformHarmonizationResult.model_validate_json(
        canonical_json_bytes(value), strict=True
    )
    upstream = result.receipt
    accepted = result.disposition is ProteoformHarmonizationDisposition.ACCEPTED
    payload: dict[str, object] = {
        "module_id": "GLIO-PROTEOGEN-M04-06",
        "receipt_version": M0407_CONTRACT_VERSION,
        "artifact_reference": ArtifactReference(
            artifact_id=f"result.m0406.{result.request_digest.removeprefix('sha256:')}",
            version=M0407_CONTRACT_VERSION,
            digest=result.result_digest,
            media_type=_M0406_RESULT_MEDIA_TYPE,
        ),
        "result_digest": result.result_digest,
        "request_digest": result.request_digest,
        "policy_digest": result.policy_digest,
        "configuration_digest": result.configuration_digest,
        "disposition": result.disposition,
        "support_status": result.support.status,
        "human_review_required": result.human_review_required,
        "completed_at": result.completed_at,
        "quality_result_digest": upstream.quality_result_digest,
        "identity_resolution_digest": upstream.identity_resolution_digest,
        "applicability": upstream.applicability,
        "assay_protocol_version": upstream.assay_protocol_version,
        "specimen_processing_version": upstream.specimen_processing_version,
        "controlled_vocabulary_id": upstream.controlled_vocabulary_id,
        "controlled_vocabulary_version": upstream.controlled_vocabulary_version,
        "unit_system_version": upstream.unit_system_version,
        "analysis_platform_level_ids": (upstream.analysis_platform_level_ids if accepted else ()),
        "analysis_target_count": upstream.analysis_target_count if accepted else None,
        "analysis_retain_target_count": (
            upstream.analysis_retain_target_count if accepted else None
        ),
        "analysis_review_target_count": (
            upstream.analysis_review_target_count if accepted else None
        ),
        "analysis_exclude_target_count": (
            upstream.analysis_exclude_target_count if accepted else None
        ),
        "analysis_evaluable_target_count": (
            upstream.analysis_evaluable_target_count if accepted else None
        ),
        "analysis_digest": upstream.analysis_digest if accepted else None,
    }
    from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
        harmonization_support_receipt_digest,
    )

    payload["receipt_digest"] = harmonization_support_receipt_digest(payload)
    return ProteoformHarmonizationSupportReceipt.model_validate(payload, strict=True)


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        # Inspect key identities before hashing or equality. A hostile colliding
        # key must not receive control during the authorization-only preflight.
        if dict.__len__(mapping) > _MAX_SHALLOW_MAPPING_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
        ):
            return None
        return dict.__getitem__(mapping, field) if dict.__contains__(mapping, field) else None
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        if (
            type(storage) is not dict
            or dict.__len__(storage) > _MAX_SHALLOW_MAPPING_ITEMS
            or any(type(key) is not str for key in dict.keys(storage))
        ):
            return None
        return dict.__getitem__(storage, field) if dict.__contains__(storage, field) else None
    return None


def _state(candidate: object) -> object:
    if type(candidate) is str:
        return candidate
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def preflight_authorized(candidate: object) -> bool:
    """Inspect only seven shallow controls before any governed payload traversal."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = (
            ("approved_configuration", UpstreamDecisionState.ACCEPTED.value),
            ("identity_lineage", IdentityLineageState.RESOLVED.value),
            ("provenance", UpstreamDecisionState.ACCEPTED.value),
            ("consent", ConsentState.GRANTED.value),
            ("quality", UpstreamDecisionState.ACCEPTED.value),
            ("support", UpstreamDecisionState.ACCEPTED.value),
            ("intended_use", UpstreamDecisionState.ACCEPTED.value),
        )
        return all(
            _state(_member(_member(references, role), "state")) == state for role, state in expected
        )
    except Exception:  # noqa: BLE001 - hostile shallow access collapses to denial.
        return False


def _validate_route_boundary(request: RouteProteoformSupportRequest) -> None:
    if not preflight_authorized(request):
        raise ValueError("proteoform support routing is not authorized")
    if request.request_id != request.context.request_id:
        raise ValueError("M04-07 request and execution context identifiers disagree")
    fact_dimensions = tuple(item.dimension for item in request.declared_facts)
    expected_facts = {
        ProteoformSupportDimension.SPECIMEN,
        ProteoformSupportDimension.DISEASE_CLASS,
        ProteoformSupportDimension.REFERENCE,
        ProteoformSupportDimension.INTENDED_USE,
    }
    if (
        len(set(fact_dimensions)) != M0407_DECLARED_FACT_COUNT
        or set(fact_dimensions) != expected_facts
    ):
        raise ValueError("route requires exactly four caller-declared support dimensions")
    roles = tuple(item.role for item in request.context_receipts)
    if len(set(roles)) != M0407_CONTEXT_RECEIPT_COUNT or set(roles) != set(ProteoformContextRole):
        raise ValueError("route requires all three context receipt roles")
    if len(request.profile.envelopes) > request.policy.max_envelopes:
        raise ValueError("support profile exceeds its reviewed policy capacity")
    from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
        configuration_digest,
    )

    references = request.context.references
    prerequisites = request.prerequisites
    if references.approved_configuration.evidence.digest != configuration_digest(
        request.profile, request.policy
    ):
        raise ValueError("approved configuration does not bind M04-07")
    if (
        references.identity_lineage.binding_digest
        != prerequisites.quality.identity_resolution_digest
        or references.quality.evidence.digest != prerequisites.quality.result_digest
        or references.support.evidence.digest != prerequisites.harmonization.result_digest
    ):
        raise ValueError("M04-07 controls do not bind the exact prerequisite chain")
    if (
        request.policy.reviewed_at > request.context.occurred_at
        or prerequisites.harmonization.completed_at > request.context.occurred_at
    ):
        raise ValueError("M04-07 policy or prerequisite chronology is impossible")
    support_route_evidence_index(request)


def support_route_evidence_index(
    request: RouteProteoformSupportRequest,
) -> tuple[EvidenceReference, ...]:
    """Return the exact de-duplicated evidence index, rejecting identity conflicts."""

    refs = request.context.references
    artifacts = [
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.profile.evidence,
        request.policy.evidence,
        request.prerequisites.quality.artifact_reference,
        request.prerequisites.harmonization.artifact_reference,
    ]
    artifacts.extend(reference for fact in request.declared_facts for reference in fact.evidence)
    artifacts.extend(
        receipt.reference for receipt in request.context_receipts if receipt.reference is not None
    )
    by_identity: dict[tuple[str, str], ArtifactReference] = {}
    for reference in artifacts:
        identity = (reference.artifact_id, reference.version)
        existing = by_identity.get(identity)
        if existing is not None and existing != reference:
            raise ValueError("one artifact identity cannot carry conflicting evidence metadata")
        by_identity[identity] = reference
    unique = {
        (item.artifact_id, item.version, item.digest, item.media_type): item
        for item in by_identity.values()
    }
    return tuple(
        EvidenceReference(
            reference=unique[key],
            role="evidence",
            claim=M0407_EVIDENCE_CLAIM,
        )
        for key in sorted(unique, key=canonical_json_bytes)
    )


def _remediation(
    envelope: ProteoformSupportEnvelope,
    dimension: ProteoformSupportDimension,
) -> ProteoformDimensionRemediation:
    return next(item for item in envelope.remediations if item.dimension is dimension)


def _assessment(  # noqa: PLR0913 - one exact dimension projection.
    envelope: ProteoformSupportEnvelope,
    dimension: ProteoformSupportDimension,
    state: ProteoformDeclaredSupportState,
    values: tuple[Identifier, ...],
    allowed: set[str],
    *,
    numeric_value_ppm: int | None = None,
    minimum_ppm: int | None = None,
    context_supported: bool = True,
    explicit_supported: bool | None = None,
) -> ProteoformDimensionAssessment:
    remediation = _remediation(envelope, dimension)
    if state is not ProteoformDeclaredSupportState.OBSERVED or not context_supported:
        decision = ProteoformDimensionSupportDecision.INDETERMINATE
        reason = remediation.indeterminate_reason_code
    elif explicit_supported is not None:
        decision = (
            ProteoformDimensionSupportDecision.SUPPORTED
            if explicit_supported
            else ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN
        )
        reason = remediation.outside_reason_code
    elif minimum_ppm is not None:
        decision = (
            ProteoformDimensionSupportDecision.SUPPORTED
            if numeric_value_ppm is not None and numeric_value_ppm >= minimum_ppm
            else ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN
        )
        reason = remediation.outside_reason_code
    else:
        decision = (
            ProteoformDimensionSupportDecision.SUPPORTED
            if set(values).issubset(allowed)
            else ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN
        )
        reason = remediation.outside_reason_code
    supported = decision is ProteoformDimensionSupportDecision.SUPPORTED
    return ProteoformDimensionAssessment(
        dimension=dimension,
        decision=decision,
        values=tuple(sorted(values)),
        numeric_value_ppm=numeric_value_ppm,
        reason_code=None if supported else reason,
        remediation_code=None if supported else remediation.remediation_code,
        remediation_path=None if supported else remediation.remediation_path,
    )


def _quality_prerequisite_releasable(
    prerequisites: ProteoformSupportPrerequisites,
) -> bool:
    return (
        prerequisites.quality.disposition is ProteoformQualityDisposition.QUALIFIED
        and prerequisites.quality.support_status in {SupportStatus.SUPPORTED, SupportStatus.LIMITED}
        and not prerequisites.quality.human_review_required
    )


def _harmonization_prerequisite_releasable(
    prerequisites: ProteoformSupportPrerequisites,
) -> bool:
    return (
        prerequisites.harmonization.disposition is ProteoformHarmonizationDisposition.ACCEPTED
        and prerequisites.harmonization.support_status is SupportStatus.LIMITED
        and not prerequisites.harmonization.human_review_required
    )


def _prerequisites_releasable(prerequisites: ProteoformSupportPrerequisites) -> bool:
    return _quality_prerequisite_releasable(
        prerequisites
    ) and _harmonization_prerequisite_releasable(prerequisites)


def _envelope_assessment(
    envelope: ProteoformSupportEnvelope,
    prerequisites: ProteoformSupportPrerequisites,
    facts: tuple[ProteoformDeclaredSupportFact, ...],
    contexts: tuple[ProteoformContextReceipt, ...],
) -> ProteoformEnvelopeAssessment:
    fact_map = {item.dimension: item for item in facts}
    context_map = {item.role: item for item in contexts}
    quality = prerequisites.quality
    harmonization = prerequisites.harmonization
    releasable = _prerequisites_releasable(prerequisites)
    assay_supported = releasable and (
        quality.applicability in envelope.applicabilities
        and quality.assay_protocol_version in envelope.approved_assay_protocol_versions
        and quality.specimen_processing_version in envelope.approved_specimen_processing_versions
        and quality.controlled_vocabulary_id in envelope.approved_controlled_vocabulary_ids
        and quality.controlled_vocabulary_version
        in envelope.approved_controlled_vocabulary_versions
        and quality.unit_system_version in envelope.approved_unit_system_versions
    )
    quality_values = tuple(sorted({item.status.value for item in quality.metrics}))
    completeness_values = tuple(
        item.value_ppm
        for item in quality.metrics
        if item.metric_code is ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS
        and item.value_ppm is not None
    )
    harmonized_ppm = (
        (
            harmonization.analysis_evaluable_target_count * M0407_RATE_SCALE
            + harmonization.analysis_target_count // 2
        )
        // harmonization.analysis_target_count
        if releasable
        and harmonization.analysis_evaluable_target_count is not None
        and harmonization.analysis_target_count is not None
        and harmonization.analysis_target_count > 0
        else None
    )
    completeness = (
        min(*completeness_values, harmonized_ppm)
        if len(completeness_values) == len(ProteoformRawInputRole) and harmonized_ppm is not None
        else None
    )
    reference_roles = {
        ProteoformContextRole.GENOME_TRANSCRIPTOME,
        ProteoformContextRole.PTM_ANNOTATIONS,
    }
    required_reference = set(envelope.required_context_roles) & reference_roles
    required_intended = set(envelope.required_context_roles) & {
        ProteoformContextRole.TREATMENT_HISTORY
    }
    reference_context = all(
        context_map[role].state is ProteoformDeclaredSupportState.OBSERVED
        for role in required_reference
    )
    intended_context = all(
        context_map[role].state is ProteoformDeclaredSupportState.OBSERVED
        for role in required_intended
    )
    specimen = fact_map[ProteoformSupportDimension.SPECIMEN]
    disease = fact_map[ProteoformSupportDimension.DISEASE_CLASS]
    reference = fact_map[ProteoformSupportDimension.REFERENCE]
    intended = fact_map[ProteoformSupportDimension.INTENDED_USE]
    dimensions = (
        _assessment(
            envelope,
            ProteoformSupportDimension.ASSAY,
            ProteoformDeclaredSupportState.OBSERVED
            if releasable
            else ProteoformDeclaredSupportState.UNKNOWN,
            ((quality.applicability.value,) if quality.applicability is not None else ()),
            set(),
            explicit_supported=assay_supported,
        ),
        _assessment(
            envelope,
            specimen.dimension,
            specimen.state,
            specimen.values,
            set(envelope.specimen_terms),
        ),
        _assessment(
            envelope,
            disease.dimension,
            disease.state,
            disease.values,
            set(envelope.disease_class_terms),
        ),
        _assessment(
            envelope,
            ProteoformSupportDimension.QUALITY,
            ProteoformDeclaredSupportState.OBSERVED
            if releasable
            else ProteoformDeclaredSupportState.UNKNOWN,
            quality_values,
            {item.value for item in envelope.quality_statuses},
        ),
        _assessment(
            envelope,
            ProteoformSupportDimension.COMPLETENESS,
            ProteoformDeclaredSupportState.OBSERVED
            if completeness is not None
            else ProteoformDeclaredSupportState.UNKNOWN,
            (),
            set(),
            numeric_value_ppm=completeness,
            minimum_ppm=envelope.minimum_completeness_ppm,
        ),
        _assessment(
            envelope,
            ProteoformSupportDimension.PLATFORM,
            ProteoformDeclaredSupportState.OBSERVED
            if releasable
            else ProteoformDeclaredSupportState.UNKNOWN,
            harmonization.analysis_platform_level_ids,
            set(envelope.platform_level_ids),
        ),
        _assessment(
            envelope,
            reference.dimension,
            reference.state,
            reference.values,
            set(envelope.reference_terms),
            context_supported=reference_context,
        ),
        _assessment(
            envelope,
            intended.dimension,
            intended.state,
            intended.values,
            set(envelope.intended_use_terms),
            context_supported=intended_context,
        ),
    )
    decisions = {item.decision for item in dimensions}
    decision = (
        ProteoformEnvelopeSupportDecision.ELIMINATED
        if ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN in decisions
        else ProteoformEnvelopeSupportDecision.PROVISIONAL
        if ProteoformDimensionSupportDecision.INDETERMINATE in decisions
        else ProteoformEnvelopeSupportDecision.CONFIRMED
    )
    return ProteoformEnvelopeAssessment(
        envelope_id=envelope.envelope_id,
        decision=decision,
        dimensions=dimensions,
    )


def _union_covers(assessments: tuple[ProteoformEnvelopeAssessment, ...]) -> bool:
    return all(
        any(
            next(item for item in envelope.dimensions if item.dimension is dimension).decision
            is ProteoformDimensionSupportDecision.SUPPORTED
            for envelope in assessments
        )
        for dimension in ProteoformSupportDimension
    )


def derive_support_route(
    prerequisites: ProteoformSupportPrerequisites,
    profile: ProteoformSupportProfile,
    facts: tuple[ProteoformDeclaredSupportFact, ...],
    contexts: tuple[ProteoformContextReceipt, ...],
) -> tuple[
    tuple[ProteoformEnvelopeAssessment, ...],
    tuple[Identifier, ...],
    tuple[ProteoformAbstention, ...],
]:
    """Derive the complete single-envelope route and every typed blocker."""

    assessments = tuple(
        sorted(
            (
                _envelope_assessment(envelope, prerequisites, facts, contexts)
                for envelope in profile.envelopes
            ),
            key=lambda item: item.envelope_id,
        )
    )
    matches = tuple(
        item.envelope_id
        for item in assessments
        if item.decision is ProteoformEnvelopeSupportDecision.CONFIRMED
    )
    if matches and _prerequisites_releasable(prerequisites):
        return assessments, matches, ()
    abstentions: list[ProteoformAbstention] = []
    upstream: tuple[
        tuple[
            Literal["GLIO-PROTEOGEN-M04-04", "GLIO-PROTEOGEN-M04-06"],
            bool,
        ],
        ...,
    ] = (
        (
            "GLIO-PROTEOGEN-M04-04",
            _quality_prerequisite_releasable(prerequisites),
        ),
        (
            "GLIO-PROTEOGEN-M04-06",
            _harmonization_prerequisite_releasable(prerequisites),
        ),
    )
    for module_id, releasable in upstream:
        if not releasable:
            abstentions.append(
                ProteoformAbstention(
                    code=ProteoformAbstentionCode.PREREQUISITE_UNRELEASABLE,
                    upstream_module_id=module_id,
                    reason_code=_opaque("reason", {"module": module_id, "state": "unreleasable"}),
                    remediation_code=_opaque(
                        "remediation", {"module": module_id, "action": "resolve"}
                    ),
                    remediation_path=ProteoformRemediationPath.RESOLVE_UPSTREAM_PREREQUISITE,
                )
            )
    for envelope in assessments:
        for dimension in envelope.dimensions:
            if dimension.decision is ProteoformDimensionSupportDecision.SUPPORTED:
                continue
            abstentions.append(
                ProteoformAbstention(
                    code=(
                        ProteoformAbstentionCode.DIMENSION_OUTSIDE_DOMAIN
                        if dimension.decision is ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN
                        else ProteoformAbstentionCode.DIMENSION_INDETERMINATE
                    ),
                    envelope_id=envelope.envelope_id,
                    dimension=dimension.dimension,
                    reason_code=dimension.reason_code or _opaque("reason", dimension.dimension),
                    remediation_code=dimension.remediation_code
                    or _opaque("remediation", dimension.dimension),
                    remediation_path=dimension.remediation_path
                    or ProteoformRemediationPath.REQUEST_GOVERNED_SUPPORT_REVIEW,
                )
            )
    if _union_covers(assessments):
        abstentions.append(
            ProteoformAbstention(
                code=ProteoformAbstentionCode.JOINT_COMBINATION_OUTSIDE_DOMAIN,
                reason_code=_opaque("reason", "joint_combination_outside_domain"),
                remediation_code=_opaque("remediation", "select_one_joint_envelope"),
                remediation_path=ProteoformRemediationPath.SELECT_ONE_REVIEWED_JOINT_ENVELOPE,
            )
        )
    unique = {canonical_json_bytes(item): item for item in abstentions}
    return assessments, (), tuple(unique[key] for key in sorted(unique))


def expected_support(disposition: ProteoformSupportDisposition) -> SupportDecision:
    if disposition is ProteoformSupportDisposition.SUPPORTED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="proteoform_support_confirmed",
            rationale="One complete reviewed proteoform support envelope was confirmed.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="proteoform_support_abstained",
        rationale="No complete reviewed proteoform support envelope was confirmed.",
    )


def expected_uncertainty(
    disposition: ProteoformSupportDisposition,
) -> UncertaintyProfile:
    del disposition
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0407_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=M0407_SENSITIVITY_NOTES,
    )


def expected_control_decisions(
    request: RouteProteoformSupportRequest,
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


def expected_provenance(
    request: RouteProteoformSupportRequest,
    *,
    _request_digest: Sha256Digest | None = None,
    _profile_digest: Sha256Digest | None = None,
    _policy_digest: Sha256Digest | None = None,
    _configuration_digest: Sha256Digest | None = None,
    _evidence: tuple[EvidenceReference, ...] | None = None,
) -> ProvenanceRecord:
    from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
        canonical_request_digest,
        configuration_digest,
        policy_digest,
        profile_digest,
    )

    request_hash = _request_digest or canonical_request_digest(request)
    active_profile_digest = _profile_digest or profile_digest(request.profile)
    active_policy_digest = _policy_digest or policy_digest(request.policy)
    active_configuration_digest = _configuration_digest or configuration_digest(
        request.profile,
        request.policy,
    )
    evidence = _evidence or support_route_evidence_index(request)
    evidence_digests = {item.reference.digest for item in evidence}
    input_digests = {
        request_hash,
        request.prerequisites.quality.receipt_digest,
        request.prerequisites.harmonization.receipt_digest,
        active_profile_digest,
        active_policy_digest,
        active_configuration_digest,
        *evidence_digests,
    }
    if request.supersedes_result_digest is not None:
        input_digests.add(request.supersedes_result_digest)
    return ProvenanceRecord(
        activity_id=f"activity.m0407.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0407_MODULE_ID,
        module_version=M0407_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(input_digests)),
        configuration_digest=active_configuration_digest,
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
                    code=M0407_ROUTING_LIMITATION_CODE,
                    statement=(
                        "This output routes support only; it does not emit protein-RNA "
                        "discordance, proteogenomic state, proteotype, subtype, protein, "
                        "proteoform, isoform, modification localization, kinase activity, "
                        "copy-number regression, multi-omics fusion, or treatment."
                    ),
                ),
                Limitation(
                    code=M0407_AUTHORITY_LIMITATION_CODE,
                    statement=(
                        "Upstream receipts and caller evidence are self-consistent but their "
                        "external issuer authority is not authenticated."
                    ),
                ),
                Limitation(
                    code=M0407_DOMAIN_LIMITATION_CODE,
                    statement=(
                        "A reviewed support envelope is a governed engineering boundary, not "
                        "assay validation, biological truth, or clinical fitness."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def _expected_support_route_bundle(
    request: RouteProteoformSupportRequest,
) -> _ExpectedSupportRouteBundle:
    from glio_proteogen.contracts.m04_07.canonical import (  # noqa: PLC0415
        canonical_request_digest,
        configuration_digest,
        policy_digest,
        profile_digest,
    )

    assessments, matches, abstentions = derive_support_route(
        request.prerequisites,
        request.profile,
        request.declared_facts,
        request.context_receipts,
    )
    disposition = (
        ProteoformSupportDisposition.SUPPORTED
        if matches
        else ProteoformSupportDisposition.ABSTAINED
    )
    request_hash = canonical_request_digest(request)
    active_profile_digest = profile_digest(request.profile)
    active_policy_digest = policy_digest(request.policy)
    active_configuration_digest = configuration_digest(request.profile, request.policy)
    evidence = support_route_evidence_index(request)
    return _ExpectedSupportRouteBundle(
        request_digest=request_hash,
        profile_digest=active_profile_digest,
        policy_digest=active_policy_digest,
        configuration_digest=active_configuration_digest,
        envelope_assessments=assessments,
        matched_envelope_ids=matches,
        abstention_reasons=abstentions,
        disposition=disposition,
        support=expected_support(disposition),
        uncertainty=expected_uncertainty(disposition),
        provenance=expected_provenance(
            request,
            _request_digest=request_hash,
            _profile_digest=active_profile_digest,
            _policy_digest=active_policy_digest,
            _configuration_digest=active_configuration_digest,
            _evidence=evidence,
        ),
        evidence=evidence,
        limitations=expected_limitations(),
    )


def _validate_result(
    result: ProteoformSupportRouteResult,
    bundle: _ExpectedSupportRouteBundle,
) -> None:
    if (
        result.request_digest != bundle.request_digest
        or result.profile_digest != bundle.profile_digest
        or result.policy_digest != bundle.policy_digest
        or result.configuration_digest != bundle.configuration_digest
    ):
        raise ValueError("M04-07 result digest bindings are inconsistent")
    if (
        result.envelope_assessments != bundle.envelope_assessments
        or result.matched_envelope_ids != bundle.matched_envelope_ids
        or result.abstention_reasons != bundle.abstention_reasons
        or result.disposition is not bundle.disposition
    ):
        raise ValueError("M04-07 result contradicts deterministic joint-envelope routing")
    if (
        result.route_id != f"route.{bundle.request_digest.removeprefix('sha256:')}"
        or result.support != bundle.support
        or result.uncertainty != bundle.uncertainty
        or result.provenance != bundle.provenance
        or result.evidence != bundle.evidence
        or result.limitations != bundle.limitations
        or result.human_review_required
        != (bundle.disposition is ProteoformSupportDisposition.ABSTAINED)
        or result.completed_at != result.request.context.occurred_at
    ):
        raise ValueError("M04-07 result envelope does not replay exactly")


__all__ = [
    "M0407_AUTHORITY_LIMITATION_CODE",
    "M0407_CONTEXT_RECEIPT_COUNT",
    "M0407_CONTRACT_VERSION",
    "M0407_DECLARED_FACT_COUNT",
    "M0407_DIMENSION_COUNT",
    "M0407_DOMAIN_LIMITATION_CODE",
    "M0407_EVIDENCE_CLAIM",
    "M0407_GATE",
    "M0407_MAX_ABSTENTIONS",
    "M0407_MAX_ANALYSIS_TARGETS",
    "M0407_MAX_APPROVED_VERSIONS",
    "M0407_MAX_CANONICAL_REQUEST_BYTES",
    "M0407_MAX_ENVELOPES",
    "M0407_MAX_EVIDENCE",
    "M0407_MAX_EVIDENCE_PER_FACT",
    "M0407_MAX_FACT_VALUES",
    "M0407_MAX_PLATFORM_LEVEL_IDS",
    "M0407_MODULE_ID",
    "M0407_OPERATION",
    "M0407_OUTPUT_MEDIA_TYPE",
    "M0407_OWNER",
    "M0407_PARENT",
    "M0407_QUALITY_METRIC_COUNT",
    "M0407_RATE_SCALE",
    "M0407_ROUTING_LIMITATION_CODE",
    "M0407_SAFETY_CLASS",
    "M0407_SENSITIVITY_NOTES",
    "M0407_UNCERTAINTY_RATIONALES",
    "M0407_ZERO_DIGEST",
    "ProteoformAbstention",
    "ProteoformAbstentionCode",
    "ProteoformContextReceipt",
    "ProteoformContextRole",
    "ProteoformDeclaredSupportFact",
    "ProteoformDeclaredSupportState",
    "ProteoformDimensionAssessment",
    "ProteoformDimensionRemediation",
    "ProteoformDimensionSupportDecision",
    "ProteoformEnvelopeAssessment",
    "ProteoformEnvelopeSupportDecision",
    "ProteoformHarmonizationSupportReceipt",
    "ProteoformQualityMetricSupportReceipt",
    "ProteoformQualitySupportReceipt",
    "ProteoformRemediationPath",
    "ProteoformSupportDimension",
    "ProteoformSupportDisposition",
    "ProteoformSupportEnvelope",
    "ProteoformSupportPolicy",
    "ProteoformSupportPrerequisites",
    "ProteoformSupportProfile",
    "ProteoformSupportRouteResult",
    "RouteProteoformSupportRequest",
    "derive_support_route",
    "expected_control_decisions",
    "expected_limitations",
    "expected_provenance",
    "expected_support",
    "expected_uncertainty",
    "harmonization_support_receipt",
    "opaque_support_identifier",
    "preflight_authorized",
    "quality_support_receipt",
    "support_route_evidence_index",
]
