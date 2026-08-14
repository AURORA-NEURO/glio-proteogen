"""Strict M04-05 proteoform artifact and contamination contracts.

The boundary consumes a genuine, digest-closed M04-04 result and bounded aggregate
evidence events. It never accepts spectra, sequences, accessions, abundance values,
identity material, or clinical claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, cast
from weakref import WeakKeyDictionary

from pydantic import (
    AwareDatetime,
    Field,
    TypeAdapter,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from glio_proteogen.contracts.m04_04 import (
    M0404_CONTRACT_VERSION,
    ProteoformQualityDisposition,
    ProteoformQualityResult,
)
from glio_proteogen.contracts.m04_05.canonical import (
    canonical_request_digest,
    configuration_digest,
    evidence_ledger_digest,
    policy_digest,
    posterior_digest,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    IdentityLineageState,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0405_MODULE_ID: Final = "GLIO-PROTEOGEN-M04-05"
M0405_OPERATION: Final = "detect_proteoform_artifacts"
M0405_CONTRACT_VERSION: Final = "1.0.0"
M0405_PARENT: Final = "protein_rna_discordance"
M0405_OWNER: Final = "Platform engineering"
M0405_SAFETY_CLASS: Final = "S2"
M0405_GATE: Final = "G1"
M0405_RATE_SCALE: Final = 1_000_000
M0405_DETECTOR_CLASS_COUNT: Final = 7
M0405_MAX_TARGETS: Final = 64
M0405_MAX_EVENTS: Final = M0405_MAX_TARGETS * M0405_DETECTOR_CLASS_COUNT
M0405_MAX_FLAGS: Final = 2 * M0405_MAX_TARGETS
M0405_MAX_FINDINGS: Final = 10
M0405_MAX_COUNT: Final = 10_000_000
M0405_MAX_PROFILES: Final = 16
M0405_MAX_APPROVED_VERSIONS: Final = 32
M0405_MAX_EVENT_EVIDENCE: Final = 8
# Seven controls + policy + selected profile + seven thresholds + optional ledger.
M0405_MAX_EVIDENCE: Final = 17
M0405_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0405_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0405_SEEDED_SENSITIVITY_FLOOR_PPM: Final = 900_000
M0405_FALSE_EXCLUSION_CEILING_PPM: Final = 50_000
M0405_COVERAGE_LOWER_PPM: Final = 850_000
M0405_COVERAGE_UPPER_PPM: Final = 950_000
_M0405_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0405_EVIDENCE_CLAIM: Final = (
    "Caller-declared content-addressed aggregate proteoform artifact evidence."
)

_OPAQUE_ID = re.compile(
    r"^(?:(?:event|flag|ledger|policy|profile|request|reviewer|target)\."
    r"|(?:activity|finding|result)\.m0405\.)[0-9a-f]{64}$"
)
_POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.policy+json"
_PROFILE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.profile+json"
_THRESHOLD_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.threshold+json"
_LEDGER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.event-ledger+json"
_EVENT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.event+json"
_VALIDATION_CAPABILITY_SEAL: Final = object()
_QUALITY_CAPABILITY_CONTEXT_KEY: Final = "_m0405_quality_replay_capability"
_REQUEST_CAPABILITY_CONTEXT_KEY: Final = "_m0405_validated_request_capability"


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _ReplayedM0404Capability:
    seal: object
    result: ProteoformQualityResult
    result_digest: Sha256Digest


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _ValidatedM0405RequestCapability:
    seal: object
    request: DetectProteoformArtifactsRequest
    request_digest: Sha256Digest


_ISSUED_QUALITY_CAPABILITIES: Final[
    WeakKeyDictionary[
        _ReplayedM0404Capability,
        tuple[ProteoformQualityResult, Sha256Digest, Sha256Digest],
    ]
] = WeakKeyDictionary()
_ISSUED_REQUEST_CAPABILITIES: Final[
    WeakKeyDictionary[
        _ValidatedM0405RequestCapability,
        tuple[DetectProteoformArtifactsRequest, Sha256Digest],
    ]
] = WeakKeyDictionary()


def _quality_capability_is_issued(capability: _ReplayedM0404Capability) -> bool:
    snapshot = _ISSUED_QUALITY_CAPABILITIES.get(capability)
    return (
        snapshot is not None
        and snapshot[0] is capability.result
        and snapshot[1] == capability.result_digest
        and capability.result.result_digest == capability.result_digest
        and snapshot[2] == sha256_digest(capability.result)
    )


def _request_capability_is_issued(capability: _ValidatedM0405RequestCapability) -> bool:
    snapshot = _ISSUED_REQUEST_CAPABILITIES.get(capability)
    return (
        snapshot is not None
        and snapshot[0] is capability.request
        and snapshot[1] == capability.request_digest
        and canonical_request_digest(capability.request) == capability.request_digest
    )


def _issue_quality_replay_capability(
    result: ProteoformQualityResult,
) -> _ReplayedM0404Capability:
    capability = _ReplayedM0404Capability(
        seal=_VALIDATION_CAPABILITY_SEAL,
        result=result,
        result_digest=result.result_digest,
    )
    _ISSUED_QUALITY_CAPABILITIES[capability] = (
        result,
        result.result_digest,
        sha256_digest(result),
    )
    return capability


def opaque_proteoform_artifact_identifier(value: Identifier, namespace: str) -> Identifier:
    """Require one content-derived local identifier without exposing source identity."""

    if _OPAQUE_ID.fullmatch(value) is None or not value.startswith(f"{namespace}."):
        raise ValueError("M04-05 identifiers require their exact opaque local namespace")
    return value


class ProteoformArtifactDetectorClass(StrEnum):
    TECHNICAL_ARTIFACT = "technical_artifact"
    CONTAMINATION = "contamination"
    BARCODE_INDEX = "barcode_index"
    BATCH_EFFECT = "batch_effect"
    LOW_COMPLEXITY = "low_complexity"
    MAPPING_ERROR = "mapping_error"
    CONTEXT_SPECIFIC_FALSE_POSITIVE = "context_specific_false_positive"


class ProteoformEvidenceUnitKind(StrEnum):
    SPECTRAL_FEATURE = "spectral_feature"
    PEPTIDE_FEATURE = "peptide_feature"
    PROTEOFORM_CANDIDATE = "proteoform_candidate"
    PTM_SITE = "ptm_site"
    BATCH_PARTITION = "batch_partition"
    SAMPLE_CONTEXT_BINDING = "sample_context_binding"


class ProteoformArtifactObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class ProteoformArtifactPosteriorState(StrEnum):
    CLEAR = "clear"
    SUSPECTED = "suspected"
    DETECTED = "detected"
    INDETERMINATE = "indeterminate"


class ProteoformArtifactDisposition(StrEnum):
    CLEARED = "cleared"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class ProteoformArtifactFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


class ProteoformArtifactFindingCode(StrEnum):
    UPSTREAM_QUARANTINED = "upstream_quarantined"
    UPSTREAM_ABSTAINED = "upstream_abstained"
    EVIDENCE_LEDGER_BINDING_MISMATCH = "evidence_ledger_binding_mismatch"
    DETECTOR_PROFILE_UNSUPPORTED = "detector_profile_unsupported"
    EVIDENCE_MISSING = "evidence_missing"
    EVIDENCE_UNSUPPORTED = "evidence_unsupported"
    EVIDENCE_NOT_EVALUABLE = "evidence_not_evaluable"
    ARTIFACT_SUSPECTED = "artifact_suspected"
    ARTIFACT_DETECTED = "artifact_detected"
    CONTAMINATION_FLAGGED = "contamination_flagged"


class ProteoformExclusionReasonCode(StrEnum):
    CRITICAL_ARTIFACT_DETECTED = "critical_artifact_detected"


class ProteoformArtifactSeverity(StrEnum):
    REVIEW = "review"
    EXCLUDE = "exclude"


_ACTION_BY_FINDING: Final = {
    ProteoformArtifactFindingCode.UPSTREAM_QUARANTINED: (
        ProteoformArtifactFindingAction.QUARANTINE
    ),
    ProteoformArtifactFindingCode.UPSTREAM_ABSTAINED: ProteoformArtifactFindingAction.ABSTAIN,
    ProteoformArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH: (
        ProteoformArtifactFindingAction.QUARANTINE
    ),
    ProteoformArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED: (
        ProteoformArtifactFindingAction.ABSTAIN
    ),
    ProteoformArtifactFindingCode.EVIDENCE_MISSING: (ProteoformArtifactFindingAction.ABSTAIN),
    ProteoformArtifactFindingCode.EVIDENCE_UNSUPPORTED: (ProteoformArtifactFindingAction.ABSTAIN),
    ProteoformArtifactFindingCode.EVIDENCE_NOT_EVALUABLE: (ProteoformArtifactFindingAction.ABSTAIN),
    ProteoformArtifactFindingCode.ARTIFACT_SUSPECTED: (ProteoformArtifactFindingAction.QUARANTINE),
    ProteoformArtifactFindingCode.ARTIFACT_DETECTED: (ProteoformArtifactFindingAction.QUARANTINE),
    ProteoformArtifactFindingCode.CONTAMINATION_FLAGGED: (
        ProteoformArtifactFindingAction.QUARANTINE
    ),
}
_MESSAGE_BY_FINDING: Final = {
    code: code.value.replace("_", " ").capitalize() + "." for code in ProteoformArtifactFindingCode
}


class ProteoformArtifactThreshold(FrozenModel):
    detector_class: ProteoformArtifactDetectorClass
    review_threshold_ppm: int = Field(ge=0, le=M0405_RATE_SCALE)
    exclusion_threshold_ppm: int = Field(ge=0, le=M0405_RATE_SCALE)
    required: bool
    evidence: ArtifactReference

    @model_validator(mode="after")
    def threshold_is_closed(self) -> ProteoformArtifactThreshold:
        if self.review_threshold_ppm > self.exclusion_threshold_ppm:
            raise ValueError("review threshold cannot exceed exclusion threshold")
        if self.evidence.media_type != _THRESHOLD_MEDIA_TYPE:
            raise ValueError("threshold evidence must use the owned media type")
        return self


class ProteoformArtifactProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    approved_quality_contract_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0405_MAX_APPROVED_VERSIONS
    )
    approved_quality_configuration_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1, max_length=M0405_MAX_APPROVED_VERSIONS
    )
    thresholds: tuple[ProteoformArtifactThreshold, ...] = Field(
        min_length=M0405_DETECTOR_CLASS_COUNT,
        max_length=M0405_DETECTOR_CLASS_COUNT,
    )
    evidence: ArtifactReference

    @field_validator("approved_quality_contract_versions")
    @classmethod
    def versions_are_canonical(
        cls, values: tuple[SemanticVersion, ...]
    ) -> tuple[SemanticVersion, ...]:
        if len(values) != len(set(values)):
            raise ValueError("approved quality contract versions must be unique")
        return tuple(sorted(values))

    @field_validator("approved_quality_configuration_digests")
    @classmethod
    def configurations_are_canonical(
        cls, values: tuple[Sha256Digest, ...]
    ) -> tuple[Sha256Digest, ...]:
        if len(values) != len(set(values)):
            raise ValueError("approved quality configuration digests must be unique")
        return tuple(sorted(values))

    @field_validator("thresholds")
    @classmethod
    def thresholds_are_canonical(
        cls, values: tuple[ProteoformArtifactThreshold, ...]
    ) -> tuple[ProteoformArtifactThreshold, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def profile_is_closed(self) -> ProteoformArtifactProfile:
        opaque_proteoform_artifact_identifier(self.profile_id, "profile")
        if {item.detector_class for item in self.thresholds} != set(
            ProteoformArtifactDetectorClass
        ):
            raise ValueError("profile requires every detector class exactly once")
        if self.evidence.media_type != _PROFILE_MEDIA_TYPE:
            raise ValueError("profile evidence must use the owned media type")
        return self


class ProteoformArtifactPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    profiles: tuple[ProteoformArtifactProfile, ...] = Field(
        min_length=1, max_length=M0405_MAX_PROFILES
    )
    quarantine_suspected: Literal[True] = True
    abstain_missing_required: Literal[True] = True
    open_set_abstention: Literal[True] = True
    never_infer_negative_from_missing: Literal[True] = True
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("profiles")
    @classmethod
    def profiles_are_canonical(
        cls, values: tuple[ProteoformArtifactProfile, ...]
    ) -> tuple[ProteoformArtifactProfile, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def policy_is_closed(self) -> ProteoformArtifactPolicy:
        opaque_proteoform_artifact_identifier(self.policy_id, "policy")
        opaque_proteoform_artifact_identifier(self.reviewed_by, "reviewer")
        if self.evidence.media_type != _POLICY_MEDIA_TYPE:
            raise ValueError("policy evidence must use the owned media type")
        identities = {(item.profile_id, item.version) for item in self.profiles}
        if len(identities) != len(self.profiles):
            raise ValueError("profile identities must be unique")
        domains: set[tuple[SemanticVersion, Sha256Digest]] = set()
        for profile in self.profiles:
            current = {
                (version, configuration)
                for version in profile.approved_quality_contract_versions
                for configuration in profile.approved_quality_configuration_digests
            }
            if domains & current:
                raise ValueError("profile quality version/configuration domains must be disjoint")
            domains.update(current)
        return self


class ProteoformArtifactEvidenceEvent(FrozenModel):
    event_id: Identifier
    sequence: int = Field(ge=1, le=M0405_MAX_EVENTS)
    target_id: Identifier
    unit_kind: ProteoformEvidenceUnitKind
    detector_class: ProteoformArtifactDetectorClass
    observation_state: ProteoformArtifactObservationState
    supporting_count: int = Field(ge=0, le=M0405_MAX_COUNT)
    evaluated_count: int = Field(ge=0, le=M0405_MAX_COUNT)
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0405_MAX_EVENT_EVIDENCE
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_canonical(
        cls, values: tuple[ArtifactReference, ...]
    ) -> tuple[ArtifactReference, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def event_is_closed(self) -> ProteoformArtifactEvidenceEvent:
        opaque_proteoform_artifact_identifier(self.event_id, "event")
        opaque_proteoform_artifact_identifier(self.target_id, "target")
        if self.supporting_count > self.evaluated_count:
            raise ValueError("supporting count cannot exceed evaluated count")
        observed = self.observation_state is ProteoformArtifactObservationState.OBSERVED
        if observed != (self.evaluated_count > 0):
            raise ValueError("only observed events carry a positive denominator")
        if not observed and (self.supporting_count != 0 or self.evaluated_count != 0):
            raise ValueError("non-observed events require exact zero counts")
        if any(item.media_type != _EVENT_MEDIA_TYPE for item in self.evidence):
            raise ValueError("event evidence must use the owned media type")
        return self


class ProteoformArtifactEvidenceLedger(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    quality_result_digest: Sha256Digest
    events: tuple[ProteoformArtifactEvidenceEvent, ...] = Field(
        min_length=M0405_DETECTOR_CLASS_COUNT,
        max_length=M0405_MAX_EVENTS,
    )
    recorded_at: AwareDatetime
    ledger_digest: Sha256Digest
    evidence: ArtifactReference

    @field_validator("events")
    @classmethod
    def events_are_sequence_ordered(
        cls, values: tuple[ProteoformArtifactEvidenceEvent, ...]
    ) -> tuple[ProteoformArtifactEvidenceEvent, ...]:
        return tuple(sorted(values, key=lambda item: item.sequence))

    @model_validator(mode="after")
    def ledger_is_closed(self) -> ProteoformArtifactEvidenceLedger:
        opaque_proteoform_artifact_identifier(self.ledger_id, "ledger")
        if self.evidence.media_type != _LEDGER_MEDIA_TYPE:
            raise ValueError("ledger evidence must use the owned media type")
        if tuple(item.sequence for item in self.events) != tuple(range(1, len(self.events) + 1)):
            raise ValueError("event sequence must be contiguous from one")
        event_ids = tuple(item.event_id for item in self.events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event identifiers must be unique")
        pairs = tuple((item.target_id, item.detector_class) for item in self.events)
        if len(pairs) != len(set(pairs)):
            raise ValueError("target and detector-class event pairs must be unique")
        target_ids = {item.target_id for item in self.events}
        for target_id in target_ids:
            target_events = tuple(item for item in self.events if item.target_id == target_id)
            if {item.detector_class for item in target_events} != set(
                ProteoformArtifactDetectorClass
            ):
                raise ValueError("every target requires all seven detector classes")
            if len({item.unit_kind for item in target_events}) != 1:
                raise ValueError("one target cannot change evidence-unit kind")
        if self.ledger_digest != evidence_ledger_digest(self):
            raise ValueError("ledger digest does not bind its canonical payload")
        return self


class ProteoformArtifactEvidenceLedgerBinding(FrozenModel):
    """Non-traversing receipt for a ledger bound to a different M04-04 result."""

    ledger_id: Identifier
    version: SemanticVersion
    quality_result_digest: Sha256Digest
    recorded_at: AwareDatetime
    ledger_digest: Sha256Digest
    evidence: ArtifactReference

    @model_validator(mode="after")
    def binding_is_closed(self) -> ProteoformArtifactEvidenceLedgerBinding:
        opaque_proteoform_artifact_identifier(self.ledger_id, "ledger")
        if self.ledger_digest == _M0405_ZERO_DIGEST:
            raise ValueError("ledger binding requires a final caller-declared digest")
        if self.evidence.media_type != _LEDGER_MEDIA_TYPE:
            raise ValueError("ledger evidence must use the owned media type")
        return self


class DetectProteoformArtifactsRequest(FrozenModel):
    operation: Literal["detect_proteoform_artifacts"] = M0405_OPERATION
    contract_version: Literal["1.0.0"] = M0405_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    quality_result: ProteoformQualityResult
    policy: ProteoformArtifactPolicy
    evidence_ledger: (
        ProteoformArtifactEvidenceLedger | ProteoformArtifactEvidenceLedgerBinding | None
    ) = None
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("quality_result", mode="wrap")
    @classmethod
    def quality_result_is_fully_replayed(
        cls,
        value: object,
        _handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> ProteoformQualityResult:
        capability = (
            info.context.get(_QUALITY_CAPABILITY_CONTEXT_KEY)
            if isinstance(info.context, dict)
            else None
        )
        if (
            isinstance(capability, _ReplayedM0404Capability)
            and capability.seal is _VALIDATION_CAPABILITY_SEAL
            and _quality_capability_is_issued(capability)
            and value is capability.result
        ):
            return capability.result
        if info.mode != "json" and type(value) is ProteoformQualityResult:
            return ProteoformQualityResult.model_validate_json(
                canonical_json_bytes(value),
                strict=True,
            )
        return ProteoformQualityResult.model_validate_json(
            canonical_json_bytes(value),
            strict=True,
        )

    @model_validator(mode="after")
    def request_is_closed(  # noqa: PLR0912 - explicit authority and traversal closure.
        self,
    ) -> DetectProteoformArtifactsRequest:
        refs = self.context.references
        upstream_refs = self.quality_result.request.context.references
        opaque_proteoform_artifact_identifier(self.request_id, "request")
        opaque_proteoform_artifact_identifier(self.context.request_id, "request")
        if self.request_id != self.context.request_id:
            raise ValueError("request identifier must equal authorized context identifier")
        if (
            any(
                item.state is not UpstreamDecisionState.ACCEPTED
                for item in (
                    refs.approved_configuration,
                    refs.provenance,
                    refs.quality,
                    refs.support,
                    refs.intended_use,
                )
            )
            or refs.identity_lineage.state is not IdentityLineageState.RESOLVED
        ):
            raise ValueError("M04-05 requires accepted and resolved upstream controls")
        if refs.consent.state is not ConsentState.GRANTED:
            raise ValueError("M04-05 requires caller-declared granted consent")
        if refs.identity_lineage != upstream_refs.identity_lineage:
            raise ValueError("identity-lineage authority must be preserved from M04-04")
        if refs.consent != upstream_refs.consent:
            raise ValueError("consent authority must be preserved from M04-04")
        if refs.provenance != upstream_refs.provenance:
            raise ValueError("provenance authority must be preserved from M04-04")
        if refs.support != upstream_refs.support:
            raise ValueError("support authority must be preserved from M04-04")
        if refs.intended_use != upstream_refs.intended_use:
            raise ValueError("intended-use authority must be preserved from M04-04")
        if self.quality_result.result_version != M0404_CONTRACT_VERSION:
            raise ValueError("M04-05 supports only the locked M04-04 contract version")
        if refs.identity_lineage.binding_digest != (
            self.quality_result.receipt.identity_resolution_digest
        ):
            raise ValueError("identity control does not bind the M04-04 receipt")
        if self.context.references.quality.evidence.digest != self.quality_result.result_digest:
            raise ValueError("quality authority evidence must bind the M04-04 result")
        if refs.approved_configuration.evidence.digest != configuration_digest(self.policy):
            raise ValueError("approved configuration must bind the detector policy")
        if (
            max(self.quality_result.completed_at, self.policy.reviewed_at)
            > self.context.occurred_at
        ):
            raise ValueError("M04-05 inputs cannot postdate artifact detection")
        matches = tuple(
            profile
            for profile in self.policy.profiles
            if (
                self.quality_result.result_version in profile.approved_quality_contract_versions
                and self.quality_result.configuration_digest
                in profile.approved_quality_configuration_digests
            )
        )
        traversable = (
            self.quality_result.disposition is ProteoformQualityDisposition.QUALIFIED
            and len(matches) == 1
        )
        if traversable != (self.evidence_ledger is not None):
            raise ValueError("evidence-ledger presence contradicts the traversal envelope")
        if self.evidence_ledger is not None and not (
            self.quality_result.completed_at
            <= self.evidence_ledger.recorded_at
            <= self.context.occurred_at
        ):
            raise ValueError("artifact events must follow M04-04 and precede detection")
        if len(matches) > 1:
            raise ValueError("request cannot select multiple detector profiles")
        _require_consistent_evidence_identities(self)
        if len(canonical_json_bytes(self)) > M0405_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M04-05 request exceeds the installed ceiling")
        return self


def _require_consistent_evidence_identities(
    request: DetectProteoformArtifactsRequest,
) -> None:
    refs = request.context.references
    artifacts = [
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
        artifacts.append(profile.evidence)
        artifacts.extend(item.evidence for item in profile.thresholds)
    if request.evidence_ledger is not None:
        artifacts.append(request.evidence_ledger.evidence)
        if isinstance(request.evidence_ledger, ProteoformArtifactEvidenceLedger):
            for event in request.evidence_ledger.events:
                artifacts.extend(event.evidence)
    seen: dict[tuple[Identifier, SemanticVersion], tuple[Sha256Digest, str]] = {}
    for artifact in artifacts:
        identity = (artifact.artifact_id, artifact.version)
        content = (artifact.digest, artifact.media_type)
        previous = seen.setdefault(identity, content)
        if previous != content:
            raise ValueError("one evidence identity cannot declare conflicting content")


def _issue_validated_request_capability(
    request: DetectProteoformArtifactsRequest,
) -> _ValidatedM0405RequestCapability:
    request_hash = canonical_request_digest(request)
    capability = _ValidatedM0405RequestCapability(
        seal=_VALIDATION_CAPABILITY_SEAL,
        request=request,
        request_digest=request_hash,
    )
    _ISSUED_REQUEST_CAPABILITIES[capability] = (request, request_hash)
    return capability


class ProteoformArtifactPosterior(FrozenModel):
    posterior_digest: Sha256Digest
    target_id: Identifier
    unit_kind: ProteoformEvidenceUnitKind
    detector_class: ProteoformArtifactDetectorClass
    observation_state: ProteoformArtifactObservationState
    state: ProteoformArtifactPosteriorState
    posterior_ppm: int | None = Field(default=None, ge=0, le=M0405_RATE_SCALE)
    lower_bound_ppm: int | None = Field(default=None, ge=0, le=M0405_RATE_SCALE)
    upper_bound_ppm: int | None = Field(default=None, ge=0, le=M0405_RATE_SCALE)
    score_is_calibrated_probability: Literal[False] = False
    support: SupportDecision
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M0405_MAX_EVENT_EVIDENCE
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_canonical(
        cls, values: tuple[EvidenceReference, ...]
    ) -> tuple[EvidenceReference, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def posterior_is_closed(self) -> ProteoformArtifactPosterior:
        opaque_proteoform_artifact_identifier(self.target_id, "target")
        observed = self.observation_state is ProteoformArtifactObservationState.OBSERVED
        values = (self.posterior_ppm, self.lower_bound_ppm, self.upper_bound_ppm)
        if observed:
            if any(value is None for value in values):
                raise ValueError("observed posterior requires a score and interval")
            if self.state is ProteoformArtifactPosteriorState.INDETERMINATE:
                raise ValueError("observed posterior cannot be indeterminate")
            lower, score, upper = self.lower_bound_ppm, self.posterior_ppm, self.upper_bound_ppm
            if lower is None or score is None or upper is None or not lower <= score <= upper:
                raise ValueError("posterior interval must contain the evidence score")
        elif any(value is not None for value in values) or (
            self.state is not ProteoformArtifactPosteriorState.INDETERMINATE
        ):
            raise ValueError("non-observed posterior remains scoreless and indeterminate")
        if self.posterior_digest != posterior_digest(self):
            raise ValueError("posterior digest does not bind its canonical payload")
        return self


class ProteoformContaminationFlag(FrozenModel):
    flag_id: Identifier
    target_id: Identifier
    detector_class: ProteoformArtifactDetectorClass
    posterior_digest: Sha256Digest
    severity: ProteoformArtifactSeverity
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M0405_MAX_EVENT_EVIDENCE
    )
    review_required: Literal[True] = True

    @field_validator("evidence")
    @classmethod
    def evidence_is_canonical(
        cls, values: tuple[EvidenceReference, ...]
    ) -> tuple[EvidenceReference, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def flag_is_closed(self) -> ProteoformContaminationFlag:
        opaque_proteoform_artifact_identifier(self.flag_id, "flag")
        opaque_proteoform_artifact_identifier(self.target_id, "target")
        if self.detector_class not in {
            ProteoformArtifactDetectorClass.CONTAMINATION,
            ProteoformArtifactDetectorClass.BARCODE_INDEX,
        }:
            raise ValueError("only contamination detector classes emit contamination flags")
        return self


class ProteoformExclusionMaskEntry(FrozenModel):
    target_id: Identifier
    triggering_posterior_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=7)
    triggering_flag_ids: tuple[Identifier, ...] = Field(default=(), max_length=2)
    reason_code: Literal[ProteoformExclusionReasonCode.CRITICAL_ARTIFACT_DETECTED]
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M0405_DETECTOR_CLASS_COUNT * M0405_MAX_EVENT_EVIDENCE
    )
    review_required: Literal[True] = True

    @field_validator("triggering_posterior_digests", "triggering_flag_ids")
    @classmethod
    def identifiers_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("exclusion-mask trigger identifiers must be unique")
        return tuple(sorted(values))

    @field_validator("evidence")
    @classmethod
    def evidence_is_canonical(
        cls, values: tuple[EvidenceReference, ...]
    ) -> tuple[EvidenceReference, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def entry_is_closed(self) -> ProteoformExclusionMaskEntry:
        opaque_proteoform_artifact_identifier(self.target_id, "target")
        for flag_id in self.triggering_flag_ids:
            opaque_proteoform_artifact_identifier(flag_id, "flag")
        return self


class ProteoformArtifactFinding(FrozenModel):
    finding_id: Identifier
    code: ProteoformArtifactFindingCode
    action: ProteoformArtifactFindingAction
    message: NonEmptyStr
    target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0405_MAX_TARGETS)
    detector_classes: tuple[ProteoformArtifactDetectorClass, ...] = Field(
        default=(), max_length=M0405_DETECTOR_CLASS_COUNT
    )

    @field_validator("target_ids", "detector_classes")
    @classmethod
    def values_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if len(values) != len(set(values)):
            raise ValueError("finding values must be unique")
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def finding_is_closed(self) -> ProteoformArtifactFinding:
        opaque_proteoform_artifact_identifier(self.finding_id, "finding.m0405")
        expected_id = "finding.m0405." + sha256_digest(
            {
                "module_id": M0405_MODULE_ID,
                "code": self.code,
                "target_ids": self.target_ids,
                "detector_classes": self.detector_classes,
            }
        ).removeprefix("sha256:")
        if self.finding_id != expected_id:
            raise ValueError("finding identifier does not bind its canonical content")
        if self.action is not _ACTION_BY_FINDING[self.code]:
            raise ValueError("finding action contradicts its code")
        if self.message != _MESSAGE_BY_FINDING[self.code]:
            raise ValueError("finding message contradicts its code")
        for target_id in self.target_ids:
            opaque_proteoform_artifact_identifier(target_id, "target")
        return self


class ProteoformArtifactComputationReceipt(FrozenModel):
    quality_result_digest: Sha256Digest
    quality_request_digest: Sha256Digest
    quality_policy_digest: Sha256Digest
    quality_configuration_digest: Sha256Digest
    quality_receipt_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    reference_bundle_digest: Sha256Digest
    coordinate_policy_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    detector_policy_digest: Sha256Digest
    detector_configuration_digest: Sha256Digest
    selected_profile_digest: Sha256Digest | None
    evidence_ledger_digest: Sha256Digest | None
    event_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=M0405_MAX_EVENTS)
    posterior_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=M0405_MAX_EVENTS)
    contamination_flag_digests: tuple[Sha256Digest, ...] = Field(
        default=(), max_length=M0405_MAX_FLAGS
    )
    excluded_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0405_MAX_TARGETS)
    finding_codes: tuple[ProteoformArtifactFindingCode, ...] = Field(
        default=(), max_length=M0405_MAX_FINDINGS
    )
    parent_target: Literal["protein_rna_discordance"] = M0405_PARENT
    emits_parent: Literal[False] = False
    disposition: ProteoformArtifactDisposition
    receipt_digest: Sha256Digest

    @field_validator(
        "event_digests",
        "posterior_digests",
        "contamination_flag_digests",
        "excluded_target_ids",
        "finding_codes",
    )
    @classmethod
    def collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if len(values) != len(set(values)):
            raise ValueError("receipt collections must be unique")
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_is_closed(self) -> ProteoformArtifactComputationReceipt:
        if len(self.event_digests) != len(self.posterior_digests):
            raise ValueError("every traversed event requires one posterior")
        if self.evidence_ledger_digest is None and any(
            (self.event_digests, self.posterior_digests, self.contamination_flag_digests)
        ):
            raise ValueError("safe-failure receipt cannot claim traversed detector output")
        if self.event_digests and self.selected_profile_digest is None:
            raise ValueError("traversed detector output requires one selected profile")
        if self.receipt_digest != receipt_digest(self):
            raise ValueError("receipt digest does not bind its canonical payload")
        return self


class ProteoformArtifactDetectionResult(FrozenModel):
    output_type: Literal["proteoform_artifact_contamination_assessment"] = (
        "proteoform_artifact_contamination_assessment"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0405_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    receipt_digest: Sha256Digest
    result_digest: Sha256Digest
    request: DetectProteoformArtifactsRequest
    receipt: ProteoformArtifactComputationReceipt
    artifact_posteriors: tuple[ProteoformArtifactPosterior, ...] = Field(
        default=(), max_length=M0405_MAX_EVENTS
    )
    contamination_flags: tuple[ProteoformContaminationFlag, ...] = Field(
        default=(), max_length=M0405_MAX_FLAGS
    )
    exclusion_mask: tuple[ProteoformExclusionMaskEntry, ...] = Field(
        default=(), max_length=M0405_MAX_TARGETS
    )
    findings: tuple[ProteoformArtifactFinding, ...] = Field(
        default=(), max_length=M0405_MAX_FINDINGS
    )
    disposition: ProteoformArtifactDisposition
    parent_target: Literal["protein_rna_discordance"] = M0405_PARENT
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=8, max_length=M0405_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("request", mode="wrap")
    @classmethod
    def request_may_reuse_sealed_validation(
        cls,
        value: object,
        handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> DetectProteoformArtifactsRequest:
        capability = (
            info.context.get(_REQUEST_CAPABILITY_CONTEXT_KEY)
            if isinstance(info.context, dict)
            else None
        )
        if (
            isinstance(capability, _ValidatedM0405RequestCapability)
            and capability.seal is _VALIDATION_CAPABILITY_SEAL
            and _request_capability_is_issued(capability)
            and value is capability.request
        ):
            return capability.request
        if info.mode == "json":
            return TypeAdapter(DetectProteoformArtifactsRequest).validate_json(
                canonical_json_bytes(value),
                strict=True,
            )
        return cast("DetectProteoformArtifactsRequest", handler(value))

    @field_validator(
        "artifact_posteriors",
        "contamination_flags",
        "exclusion_mask",
        "findings",
        "evidence",
        "limitations",
    )
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
    def result_is_digest_closed(  # noqa: PLR0912 - explicit closure checks.
        self,
    ) -> ProteoformArtifactDetectionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest is stale")
        if self.policy_digest != policy_digest(self.request.policy):
            raise ValueError("result policy digest is stale")
        if self.configuration_digest != configuration_digest(self.request.policy):
            raise ValueError("result configuration digest is stale")
        if self.receipt_digest != self.receipt.receipt_digest:
            raise ValueError("result receipt digest is stale")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not bind its canonical payload")
        if self.receipt.quality_result_digest != self.request.quality_result.result_digest:
            raise ValueError("result receipt does not bind M04-04")
        if self.receipt.identity_resolution_digest != (
            self.request.quality_result.receipt.identity_resolution_digest
        ):
            raise ValueError("result receipt does not preserve identity-resolution binding")
        posterior_index = {item.posterior_digest: item for item in self.artifact_posteriors}
        if len(posterior_index) != len(self.artifact_posteriors):
            raise ValueError("posterior digests must be unique")
        if set(self.receipt.posterior_digests) != set(posterior_index):
            raise ValueError("receipt posterior closure is incomplete")
        flag_index = {item.flag_id: item for item in self.contamination_flags}
        if len(flag_index) != len(self.contamination_flags):
            raise ValueError("contamination flag identifiers must be unique")
        target_ids = tuple(item.target_id for item in self.exclusion_mask)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("exclusion mask can contain each target only once")
        for flag in self.contamination_flags:
            posterior = posterior_index.get(flag.posterior_digest)
            if posterior is None or posterior.target_id != flag.target_id:
                raise ValueError("contamination flag must bind one emitted posterior")
        for entry in self.exclusion_mask:
            if any(digest not in posterior_index for digest in entry.triggering_posterior_digests):
                raise ValueError("exclusion mask references an unknown posterior")
            if any(flag_id not in flag_index for flag_id in entry.triggering_flag_ids):
                raise ValueError("exclusion mask references an unknown contamination flag")
        if len(canonical_json_bytes(self)) > M0405_MAX_CANONICAL_RESULT_BYTES:
            raise ValueError("canonical M04-05 result exceeds the installed ceiling")
        return self

    @model_validator(mode="after")
    def result_is_exactly_rederived(self) -> ProteoformArtifactDetectionResult:
        from glio_proteogen.contracts.m04_05.derivation import (  # noqa: PLC0415
            expected_detection_bundle,
            expected_result_id,
        )

        bundle = expected_detection_bundle(self.request)
        if self.result_id != expected_result_id(self.request):
            raise ValueError("result identifier does not bind the canonical request")
        regions: tuple[tuple[str, object, object], ...] = (
            ("artifact posteriors", self.artifact_posteriors, bundle.artifact_posteriors),
            ("contamination flags", self.contamination_flags, bundle.contamination_flags),
            ("exclusion mask", self.exclusion_mask, bundle.exclusion_mask),
            ("findings", self.findings, bundle.findings),
            ("disposition", self.disposition, bundle.disposition),
            ("receipt", self.receipt, bundle.receipt),
            ("support", self.support, bundle.support),
            ("uncertainty", self.uncertainty, bundle.uncertainty),
            ("provenance", self.provenance, bundle.provenance),
            ("evidence", self.evidence, bundle.evidence),
            ("limitations", self.limitations, bundle.limitations),
            ("review state", self.human_review_required, bundle.human_review_required),
            ("completion time", self.completed_at, self.request.context.occurred_at),
        )
        for label, actual, expected in regions:
            if actual != expected:
                raise ValueError(f"result {label} contradicts exact deterministic derivation")
        return self


__all__ = [
    "M0405_CONTRACT_VERSION",
    "M0405_COVERAGE_LOWER_PPM",
    "M0405_COVERAGE_UPPER_PPM",
    "M0405_DETECTOR_CLASS_COUNT",
    "M0405_EVIDENCE_CLAIM",
    "M0405_FALSE_EXCLUSION_CEILING_PPM",
    "M0405_GATE",
    "M0405_MAX_APPROVED_VERSIONS",
    "M0405_MAX_CANONICAL_REQUEST_BYTES",
    "M0405_MAX_CANONICAL_RESULT_BYTES",
    "M0405_MAX_COUNT",
    "M0405_MAX_EVENTS",
    "M0405_MAX_EVENT_EVIDENCE",
    "M0405_MAX_EVIDENCE",
    "M0405_MAX_FINDINGS",
    "M0405_MAX_FLAGS",
    "M0405_MAX_PROFILES",
    "M0405_MAX_TARGETS",
    "M0405_MODULE_ID",
    "M0405_OPERATION",
    "M0405_OWNER",
    "M0405_PARENT",
    "M0405_RATE_SCALE",
    "M0405_SAFETY_CLASS",
    "M0405_SEEDED_SENSITIVITY_FLOOR_PPM",
    "DetectProteoformArtifactsRequest",
    "ProteoformArtifactComputationReceipt",
    "ProteoformArtifactDetectionResult",
    "ProteoformArtifactDetectorClass",
    "ProteoformArtifactDisposition",
    "ProteoformArtifactEvidenceEvent",
    "ProteoformArtifactEvidenceLedger",
    "ProteoformArtifactEvidenceLedgerBinding",
    "ProteoformArtifactFinding",
    "ProteoformArtifactFindingAction",
    "ProteoformArtifactFindingCode",
    "ProteoformArtifactObservationState",
    "ProteoformArtifactPolicy",
    "ProteoformArtifactPosterior",
    "ProteoformArtifactPosteriorState",
    "ProteoformArtifactProfile",
    "ProteoformArtifactSeverity",
    "ProteoformArtifactThreshold",
    "ProteoformContaminationFlag",
    "ProteoformEvidenceUnitKind",
    "ProteoformExclusionMaskEntry",
    "ProteoformExclusionReasonCode",
    "opaque_proteoform_artifact_identifier",
]
