"""Strict M04-05 proteoform artifact and contamination contracts.

The boundary consumes a genuine, digest-closed M04-04 result and bounded aggregate
evidence events. It never accepts spectra, sequences, accessions, abundance values,
identity material, or clinical claims.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

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
from glio_proteogen.kernel.canonical import canonical_json_bytes
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
    UncertaintyProfile,
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
M0405_MAX_TARGETS: Final = 512
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

_OPAQUE_ID = re.compile(r"^(?:event|flag|ledger|policy|profile|reviewer|target)\.[0-9a-f]{64}$")
_POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.policy+json"
_PROFILE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.profile+json"
_THRESHOLD_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.threshold+json"
_LEDGER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.event-ledger+json"
_EVENT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05.event+json"


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
    EVIDENCE_LEDGER_REQUIRED = "evidence_ledger_required"
    EVIDENCE_LEDGER_BINDING_MISMATCH = "evidence_ledger_binding_mismatch"
    DETECTOR_PROFILE_UNSUPPORTED = "detector_profile_unsupported"
    REQUIRED_EVIDENCE_MISSING = "required_evidence_missing"
    REQUIRED_EVIDENCE_UNSUPPORTED = "required_evidence_unsupported"
    ARTIFACT_SUSPECTED = "artifact_suspected"
    ARTIFACT_DETECTED = "artifact_detected"
    CONTAMINATION_FLAGGED = "contamination_flagged"


class ProteoformExclusionReasonCode(StrEnum):
    CRITICAL_ARTIFACT_DETECTED = "critical_artifact_detected"


class ProteoformArtifactSeverity(StrEnum):
    REVIEW = "review"
    EXCLUDE = "exclude"


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
        domains: set[SemanticVersion] = set()
        for profile in self.profiles:
            current = set(profile.approved_quality_contract_versions)
            if domains & current:
                raise ValueError("profile quality-version match domains must be disjoint")
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


class DetectProteoformArtifactsRequest(FrozenModel):
    context: ExecutionContext
    quality_result: ProteoformQualityResult
    policy: ProteoformArtifactPolicy
    evidence_ledger: ProteoformArtifactEvidenceLedger | None

    @model_validator(mode="after")
    def request_is_closed(self) -> DetectProteoformArtifactsRequest:
        if self.quality_result.result_version != M0404_CONTRACT_VERSION:
            raise ValueError("M04-05 supports only the locked M04-04 contract version")
        if self.context.references.quality.evidence.digest != self.quality_result.result_digest:
            raise ValueError("quality authority evidence must bind the M04-04 result")
        if self.quality_result.disposition is ProteoformQualityDisposition.QUALIFIED:
            if self.evidence_ledger is None:
                raise ValueError("qualified M04-04 input requires an evidence ledger")
            if self.evidence_ledger.quality_result_digest != self.quality_result.result_digest:
                raise ValueError("evidence ledger must bind the M04-04 result")
        elif self.evidence_ledger is not None:
            raise ValueError("nonqualified M04-04 input prohibits evidence-ledger traversal")
        matches = tuple(
            profile
            for profile in self.policy.profiles
            if self.quality_result.result_version in profile.approved_quality_contract_versions
        )
        if len(matches) != 1:
            raise ValueError("request must select exactly one reviewed detector profile")
        if len(canonical_json_bytes(self)) > M0405_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M04-05 request exceeds the installed ceiling")
        return self


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
    selected_profile_digest: Sha256Digest
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=16, max_length=M0405_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime

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
