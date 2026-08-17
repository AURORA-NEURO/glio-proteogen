"""Strict M05-05 PTM-localization artifact and contamination contracts."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m05_03 import (
    PtmLocalizationRawInputDisposition,
    PtmLocalizationRawInputValidationResult,
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

M0505_MODULE_ID: Final = "GLIO-PROTEOGEN-M05-05"
M0505_OPERATION: Final = "detect_ptm_localization_artifacts"
M0505_CONTRACT_VERSION: Final = "1.0.0"
M0505_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05+json"
M0505_PARENT: Final = "variant_peptide"
M0505_OWNER: Final = "Scientific engineering"
M0505_SAFETY_CLASS: Final = "S2"
M0505_GATE: Final = "G1"
M0505_RATE_SCALE: Final = 1_000_000
M0505_DETECTOR_CLASS_COUNT: Final = 7
M0505_MAX_TARGETS: Final = 64
M0505_MAX_EVENTS: Final = M0505_MAX_TARGETS * M0505_DETECTOR_CLASS_COUNT
M0505_MAX_FLAGS: Final = 2 * M0505_MAX_TARGETS
M0505_MAX_FINDINGS: Final = 10
M0505_MAX_COUNT: Final = 9_223_372_036_854_775_807
M0505_MAX_PROFILES: Final = 16
M0505_MAX_APPROVED_VERSIONS: Final = 32
M0505_MAX_EVENT_EVIDENCE: Final = 8
M0505_MAX_EVIDENCE: Final = 17
M0505_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0505_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0505_SEEDED_SENSITIVITY_FLOOR_PPM: Final = 900_000
M0505_FALSE_EXCLUSION_CEILING_PPM: Final = 50_000
M0505_COVERAGE_LOWER_PPM: Final = 850_000
M0505_COVERAGE_UPPER_PPM: Final = 950_000
M0505_BENCHMARK_ITERATIONS: Final = 25
M0505_BENCHMARK_WARMUPS: Final = 1
M0505_MEAN_BUDGET_NS: Final = 2_000_000_000
M0505_P95_BUDGET_NS: Final = 3_000_000_000
M0505_EVIDENCE_CLAIM: Final = (
    "Caller-declared content-addressed M05-05 aggregate artifact evidence."
)

_OPAQUE_IDENTIFIER = re.compile(
    r"^(?:request|profile|policy|threshold|event|ledger|target|posterior|flag|"
    r"finding\.m0505|evidence|reviewer|result)\.[0-9a-f]{64}$"
)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_THRESHOLD_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.threshold+json"
_PROFILE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.profile+json"
_POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.policy+json"
_EVENT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.event+json"
_LEDGER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.ledger+json"


def opaque_ptm_localization_artifact_identifier(value: Identifier, namespace: str) -> Identifier:
    """Validate one exact module-owned opaque identifier namespace."""

    if _OPAQUE_IDENTIFIER.fullmatch(value) is None or not value.startswith(f"{namespace}."):
        raise ValueError("M05-05 identifier does not use its exact opaque namespace")
    return value


def _require_owned_evidence(reference: ArtifactReference, media_type: str) -> None:
    opaque_ptm_localization_artifact_identifier(reference.artifact_id, "evidence")
    if reference.media_type != media_type:
        raise ValueError("M05-05 evidence does not use its exact owned media type")


def _canonical_unique[T](values: tuple[T, ...], label: str) -> tuple[T, ...]:
    if len(values) != len({canonical_json_bytes(item) for item in values}):
        raise ValueError(f"{label} must be unique")
    return tuple(sorted(values, key=canonical_json_bytes))


class PtmLocalizationArtifactDetectorClass(StrEnum):
    TECHNICAL_ARTIFACT = "technical_artifact"
    CONTAMINATION = "contamination"
    BARCODE_INDEX = "barcode_index"
    BATCH_EFFECT = "batch_effect"
    LOW_COMPLEXITY = "low_complexity"
    MAPPING_ERROR = "mapping_error"
    CONTEXT_SPECIFIC_FALSE_POSITIVE = "context_specific_false_positive"


class PtmLocalizationEvidenceUnitKind(StrEnum):
    SPECTRAL_FEATURE = "spectral_feature"
    VARIANT_PEPTIDE = "variant_peptide"
    PTM_SITE = "ptm_site"
    LOCALIZATION_CANDIDATE = "localization_candidate"
    BATCH_PARTITION = "batch_partition"
    SAMPLE_CONTEXT_BINDING = "sample_context_binding"


class PtmLocalizationArtifactObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class PtmLocalizationArtifactPosteriorState(StrEnum):
    CLEAR = "clear"
    SUSPECTED = "suspected"
    DETECTED = "detected"
    INDETERMINATE = "indeterminate"


class PtmLocalizationArtifactDisposition(StrEnum):
    CLEARED = "cleared"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class PtmLocalizationArtifactUpstreamDisposition(StrEnum):
    QUALIFIED = "qualified"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class PtmLocalizationArtifactFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


class PtmLocalizationArtifactFindingCode(StrEnum):
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


class PtmLocalizationExclusionReasonCode(StrEnum):
    CRITICAL_ARTIFACT_DETECTED = "critical_artifact_detected"


class PtmLocalizationArtifactSeverity(StrEnum):
    REVIEW = "review"
    EXCLUDE = "exclude"


_ACTION_BY_FINDING: Final = {
    PtmLocalizationArtifactFindingCode.UPSTREAM_QUARANTINED: (
        PtmLocalizationArtifactFindingAction.QUARANTINE
    ),
    PtmLocalizationArtifactFindingCode.UPSTREAM_ABSTAINED: (
        PtmLocalizationArtifactFindingAction.ABSTAIN
    ),
    PtmLocalizationArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH: (
        PtmLocalizationArtifactFindingAction.QUARANTINE
    ),
    PtmLocalizationArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED: (
        PtmLocalizationArtifactFindingAction.ABSTAIN
    ),
    PtmLocalizationArtifactFindingCode.EVIDENCE_MISSING: (
        PtmLocalizationArtifactFindingAction.ABSTAIN
    ),
    PtmLocalizationArtifactFindingCode.EVIDENCE_UNSUPPORTED: (
        PtmLocalizationArtifactFindingAction.ABSTAIN
    ),
    PtmLocalizationArtifactFindingCode.EVIDENCE_NOT_EVALUABLE: (
        PtmLocalizationArtifactFindingAction.ABSTAIN
    ),
    PtmLocalizationArtifactFindingCode.ARTIFACT_SUSPECTED: (
        PtmLocalizationArtifactFindingAction.QUARANTINE
    ),
    PtmLocalizationArtifactFindingCode.ARTIFACT_DETECTED: (
        PtmLocalizationArtifactFindingAction.QUARANTINE
    ),
    PtmLocalizationArtifactFindingCode.CONTAMINATION_FLAGGED: (
        PtmLocalizationArtifactFindingAction.QUARANTINE
    ),
}


class PtmLocalizationArtifactThreshold(FrozenModel):
    detector_class: PtmLocalizationArtifactDetectorClass
    review_threshold_ppm: int = Field(ge=0, le=M0505_RATE_SCALE)
    exclusion_threshold_ppm: int = Field(ge=0, le=M0505_RATE_SCALE)
    required: bool
    evidence: ArtifactReference

    @model_validator(mode="after")
    def threshold_is_closed(self) -> PtmLocalizationArtifactThreshold:
        if self.review_threshold_ppm > self.exclusion_threshold_ppm:
            raise ValueError("review threshold cannot exceed exclusion threshold")
        _require_owned_evidence(self.evidence, _THRESHOLD_MEDIA_TYPE)
        return self


class PtmLocalizationArtifactProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    approved_quality_contract_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0505_MAX_APPROVED_VERSIONS
    )
    approved_quality_configuration_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1, max_length=M0505_MAX_APPROVED_VERSIONS
    )
    thresholds: tuple[PtmLocalizationArtifactThreshold, ...] = Field(
        min_length=M0505_DETECTOR_CLASS_COUNT,
        max_length=M0505_DETECTOR_CLASS_COUNT,
    )
    evidence: ArtifactReference

    @field_validator(
        "approved_quality_contract_versions",
        "approved_quality_configuration_digests",
        "thresholds",
    )
    @classmethod
    def collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return _canonical_unique(values, "profile collections")

    @model_validator(mode="after")
    def profile_is_closed(self) -> PtmLocalizationArtifactProfile:
        opaque_ptm_localization_artifact_identifier(self.profile_id, "profile")
        if {item.detector_class for item in self.thresholds} != set(
            PtmLocalizationArtifactDetectorClass
        ):
            raise ValueError("profile requires every detector class exactly once")
        _require_owned_evidence(self.evidence, _PROFILE_MEDIA_TYPE)
        return self


class PtmLocalizationArtifactPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    profiles: tuple[PtmLocalizationArtifactProfile, ...] = Field(
        min_length=1, max_length=M0505_MAX_PROFILES
    )
    seeded_sensitivity_floor_ppm: Literal[900000] = M0505_SEEDED_SENSITIVITY_FLOOR_PPM
    false_exclusion_ceiling_ppm: Literal[50000] = M0505_FALSE_EXCLUSION_CEILING_PPM
    coverage_lower_ppm: Literal[850000] = M0505_COVERAGE_LOWER_PPM
    coverage_upper_ppm: Literal[950000] = M0505_COVERAGE_UPPER_PPM
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
        cls, values: tuple[PtmLocalizationArtifactProfile, ...]
    ) -> tuple[PtmLocalizationArtifactProfile, ...]:
        return _canonical_unique(values, "profiles")

    @model_validator(mode="after")
    def policy_is_closed(self) -> PtmLocalizationArtifactPolicy:
        opaque_ptm_localization_artifact_identifier(self.policy_id, "policy")
        opaque_ptm_localization_artifact_identifier(self.reviewed_by, "reviewer")
        _require_owned_evidence(self.evidence, _POLICY_MEDIA_TYPE)
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


class PtmLocalizationArtifactEvidenceEvent(FrozenModel):
    event_id: Identifier
    sequence: int = Field(ge=1, le=M0505_MAX_EVENTS)
    target_id: Identifier
    unit_kind: PtmLocalizationEvidenceUnitKind
    detector_class: PtmLocalizationArtifactDetectorClass
    observation_state: PtmLocalizationArtifactObservationState
    supporting_count: int = Field(ge=0, le=M0505_MAX_COUNT)
    evaluated_count: int = Field(ge=0, le=M0505_MAX_COUNT)
    seeded_critical: bool = False
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0505_MAX_EVENT_EVIDENCE
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_canonical(
        cls, values: tuple[ArtifactReference, ...]
    ) -> tuple[ArtifactReference, ...]:
        return _canonical_unique(values, "event evidence")

    @model_validator(mode="after")
    def event_is_closed(self) -> PtmLocalizationArtifactEvidenceEvent:
        opaque_ptm_localization_artifact_identifier(self.event_id, "event")
        opaque_ptm_localization_artifact_identifier(self.target_id, "target")
        if self.supporting_count > self.evaluated_count:
            raise ValueError("supporting count cannot exceed evaluated count")
        observed = self.observation_state is PtmLocalizationArtifactObservationState.OBSERVED
        if observed != (self.evaluated_count > 0):
            raise ValueError("only observed events carry a positive denominator")
        if not observed and (self.supporting_count != 0 or self.seeded_critical):
            raise ValueError("non-observed evidence cannot claim counts or seeded artifacts")
        for reference in self.evidence:
            _require_owned_evidence(reference, _EVENT_MEDIA_TYPE)
        return self


class PtmLocalizationArtifactEvidenceLedger(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    quality_result_digest: Sha256Digest
    quality_contract_version: SemanticVersion
    quality_configuration_digest: Sha256Digest
    quality_receipt_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    raw_input_receipt_digest: Sha256Digest
    events: tuple[PtmLocalizationArtifactEvidenceEvent, ...] = Field(
        min_length=M0505_DETECTOR_CLASS_COUNT,
        max_length=M0505_MAX_EVENTS,
    )
    recorded_at: AwareDatetime
    ledger_digest: Sha256Digest
    evidence: ArtifactReference

    @field_validator("events")
    @classmethod
    def events_are_sequence_ordered(
        cls, values: tuple[PtmLocalizationArtifactEvidenceEvent, ...]
    ) -> tuple[PtmLocalizationArtifactEvidenceEvent, ...]:
        return tuple(sorted(values, key=lambda item: item.sequence))

    @model_validator(mode="after")
    def ledger_is_closed(self) -> PtmLocalizationArtifactEvidenceLedger:
        from glio_proteogen.contracts.m05_05.canonical import (  # noqa: PLC0415
            evidence_ledger_digest,
        )

        opaque_ptm_localization_artifact_identifier(self.ledger_id, "ledger")
        _require_owned_evidence(self.evidence, _LEDGER_MEDIA_TYPE)
        if tuple(event.sequence for event in self.events) != tuple(range(1, len(self.events) + 1)):
            raise ValueError("event sequence must be contiguous from one")
        pairs = tuple((event.target_id, event.detector_class) for event in self.events)
        if len(pairs) != len(set(pairs)):
            raise ValueError("target/detector event pairs must be unique")
        for target_id in {event.target_id for event in self.events}:
            detector_classes = {
                event.detector_class for event in self.events if event.target_id == target_id
            }
            if detector_classes != set(PtmLocalizationArtifactDetectorClass):
                raise ValueError("every target requires all seven detector classes")
        if self.ledger_digest != evidence_ledger_digest(self):
            raise ValueError("ledger digest does not bind its canonical payload")
        return self


class PtmLocalizationArtifactEvidenceLedgerBinding(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    quality_result_digest: Sha256Digest
    quality_contract_version: SemanticVersion
    quality_configuration_digest: Sha256Digest
    quality_receipt_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    raw_input_receipt_digest: Sha256Digest
    recorded_at: AwareDatetime
    ledger_digest: Sha256Digest
    evidence: ArtifactReference

    @model_validator(mode="after")
    def binding_is_closed(self) -> PtmLocalizationArtifactEvidenceLedgerBinding:
        opaque_ptm_localization_artifact_identifier(self.ledger_id, "ledger")
        if self.ledger_digest == _ZERO_DIGEST:
            raise ValueError("ledger binding requires a final caller-declared digest")
        _require_owned_evidence(self.evidence, _LEDGER_MEDIA_TYPE)
        return self


class DetectPtmLocalizationArtifactsRequest(FrozenModel):
    operation: Literal["detect_ptm_localization_artifacts"] = M0505_OPERATION
    contract_version: Literal["1.0.0"] = M0505_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    raw_input_result: PtmLocalizationRawInputValidationResult
    quality_result_digest: Sha256Digest
    quality_contract_version: SemanticVersion
    quality_configuration_digest: Sha256Digest
    quality_receipt_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    raw_input_receipt_digest: Sha256Digest
    quality_disposition: PtmLocalizationArtifactUpstreamDisposition
    policy: PtmLocalizationArtifactPolicy
    evidence_ledger: (
        PtmLocalizationArtifactEvidenceLedger | PtmLocalizationArtifactEvidenceLedgerBinding | None
    ) = None
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("raw_input_result", mode="before")
    @classmethod
    def raw_input_result_is_strictly_replayed(
        cls, value: object
    ) -> PtmLocalizationRawInputValidationResult:
        return PtmLocalizationRawInputValidationResult.model_validate_json(
            canonical_json_bytes(value),
            strict=True,
        )

    @model_validator(mode="after")
    def request_is_closed(self) -> DetectPtmLocalizationArtifactsRequest:  # noqa: PLR0912
        from glio_proteogen.contracts.m05_05.canonical import (  # noqa: PLC0415
            configuration_digest,
        )

        refs = self.context.references
        opaque_ptm_localization_artifact_identifier(self.request_id, "request")
        opaque_ptm_localization_artifact_identifier(self.context.request_id, "request")
        if self.request_id != self.context.request_id:
            raise ValueError("request identifier must equal its authorized context identifier")
        if (
            any(
                reference.state is not UpstreamDecisionState.ACCEPTED
                for reference in (
                    refs.approved_configuration,
                    refs.provenance,
                    refs.quality,
                    refs.support,
                    refs.intended_use,
                )
            )
            or refs.identity_lineage.state is not IdentityLineageState.RESOLVED
            or refs.consent.state is not ConsentState.GRANTED
        ):
            raise ValueError("M05-05 requires all seven authorized upstream controls")
        if refs.quality.evidence.digest != self.quality_result_digest:
            raise ValueError("quality authority must bind the exact upstream result")
        if refs.identity_lineage.binding_digest != self.identity_resolution_digest:
            raise ValueError("identity authority must bind the upstream quality chain")
        if (
            self.raw_input_receipt_digest != self.raw_input_result.receipt.receipt_digest
            or self.identity_resolution_digest
            != self.raw_input_result.receipt.identity_resolution_digest
        ):
            raise ValueError("M05-03 replay does not bind the declared upstream receipts")
        raw_refs = self.raw_input_result.request.context.references
        if any(
            current != upstream
            for current, upstream in (
                (refs.identity_lineage, raw_refs.identity_lineage),
                (refs.consent, raw_refs.consent),
                (refs.provenance, raw_refs.provenance),
                (refs.support, raw_refs.support),
                (refs.intended_use, raw_refs.intended_use),
            )
        ):
            raise ValueError("M05-05 must preserve M05-03 control authority exactly")
        if refs.approved_configuration.evidence.digest != configuration_digest(self.policy):
            raise ValueError("approved configuration must bind the detector policy")
        matches = tuple(
            profile
            for profile in self.policy.profiles
            if self.quality_contract_version in profile.approved_quality_contract_versions
            and self.quality_configuration_digest in profile.approved_quality_configuration_digests
        )
        qualified = self.quality_disposition is PtmLocalizationArtifactUpstreamDisposition.QUALIFIED
        if qualified and (
            self.raw_input_result.disposition is not PtmLocalizationRawInputDisposition.VALIDATED
        ):
            raise ValueError("qualified artifact traversal requires validated M05-03 inputs")
        if qualified != (len(matches) == 1 and self.evidence_ledger is not None):
            raise ValueError("upstream disposition contradicts profile and ledger traversal")
        if self.evidence_ledger is not None:
            if not self.context.occurred_at >= self.evidence_ledger.recorded_at:
                raise ValueError("artifact evidence cannot postdate detection")
            if isinstance(self.evidence_ledger, PtmLocalizationArtifactEvidenceLedger) and (
                self.evidence_ledger.quality_result_digest != self.quality_result_digest
                or self.evidence_ledger.quality_contract_version != self.quality_contract_version
                or self.evidence_ledger.quality_configuration_digest
                != self.quality_configuration_digest
                or self.evidence_ledger.quality_receipt_digest != self.quality_receipt_digest
                or self.evidence_ledger.identity_resolution_digest
                != self.identity_resolution_digest
                or self.evidence_ledger.raw_input_receipt_digest != self.raw_input_receipt_digest
            ):
                raise ValueError("evidence ledger does not bind the exact upstream quality chain")
        if len(canonical_json_bytes(self)) > M0505_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M05-05 request exceeds the installed ceiling")
        return self


class PtmLocalizationArtifactPosterior(FrozenModel):
    posterior_digest: Sha256Digest
    target_id: Identifier
    unit_kind: PtmLocalizationEvidenceUnitKind
    detector_class: PtmLocalizationArtifactDetectorClass
    observation_state: PtmLocalizationArtifactObservationState
    state: PtmLocalizationArtifactPosteriorState
    posterior_ppm: int | None = Field(default=None, ge=0, le=M0505_RATE_SCALE)
    lower_bound_ppm: int | None = Field(default=None, ge=0, le=M0505_RATE_SCALE)
    upper_bound_ppm: int | None = Field(default=None, ge=0, le=M0505_RATE_SCALE)
    score_is_calibrated_probability: Literal[False] = False
    support: SupportDecision
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M0505_MAX_EVENT_EVIDENCE
    )

    @model_validator(mode="after")
    def posterior_is_closed(self) -> PtmLocalizationArtifactPosterior:
        from glio_proteogen.contracts.m05_05.canonical import posterior_digest  # noqa: PLC0415

        opaque_ptm_localization_artifact_identifier(self.target_id, "target")
        observed = self.observation_state is PtmLocalizationArtifactObservationState.OBSERVED
        bounds = (self.lower_bound_ppm, self.posterior_ppm, self.upper_bound_ppm)
        if observed:
            if any(value is None for value in bounds):
                raise ValueError("observed posterior requires a score and interval")
            lower, score, upper = bounds
            if lower is None or score is None or upper is None or not lower <= score <= upper:
                raise ValueError("posterior interval must contain its score")
            if self.state is PtmLocalizationArtifactPosteriorState.INDETERMINATE:
                raise ValueError("observed posterior cannot be indeterminate")
        elif any(value is not None for value in bounds) or (
            self.state is not PtmLocalizationArtifactPosteriorState.INDETERMINATE
        ):
            raise ValueError("non-observed posterior must remain scoreless and indeterminate")
        if self.posterior_digest != posterior_digest(self):
            raise ValueError("posterior digest does not bind its canonical payload")
        return self


class PtmLocalizationContaminationFlag(FrozenModel):
    flag_id: Identifier
    target_id: Identifier
    detector_class: PtmLocalizationArtifactDetectorClass
    posterior_digest: Sha256Digest
    severity: PtmLocalizationArtifactSeverity
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M0505_MAX_EVENT_EVIDENCE
    )
    review_required: Literal[True] = True

    @model_validator(mode="after")
    def flag_is_closed(self) -> PtmLocalizationContaminationFlag:
        opaque_ptm_localization_artifact_identifier(self.flag_id, "flag")
        opaque_ptm_localization_artifact_identifier(self.target_id, "target")
        if self.detector_class not in {
            PtmLocalizationArtifactDetectorClass.CONTAMINATION,
            PtmLocalizationArtifactDetectorClass.BARCODE_INDEX,
        }:
            raise ValueError("only contamination detector classes emit contamination flags")
        return self


class PtmLocalizationExclusionMaskEntry(FrozenModel):
    target_id: Identifier
    triggering_posterior_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1, max_length=M0505_DETECTOR_CLASS_COUNT
    )
    triggering_flag_ids: tuple[Identifier, ...] = Field(default=(), max_length=2)
    reason_code: Literal[PtmLocalizationExclusionReasonCode.CRITICAL_ARTIFACT_DETECTED] = (
        PtmLocalizationExclusionReasonCode.CRITICAL_ARTIFACT_DETECTED
    )
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1,
        max_length=M0505_DETECTOR_CLASS_COUNT * M0505_MAX_EVENT_EVIDENCE,
    )
    review_required: Literal[True] = True

    @field_validator("triggering_posterior_digests", "triggering_flag_ids")
    @classmethod
    def triggers_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("exclusion triggers must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def entry_is_closed(self) -> PtmLocalizationExclusionMaskEntry:
        opaque_ptm_localization_artifact_identifier(self.target_id, "target")
        for flag_id in self.triggering_flag_ids:
            opaque_ptm_localization_artifact_identifier(flag_id, "flag")
        return self


class PtmLocalizationArtifactFinding(FrozenModel):
    finding_id: Identifier
    code: PtmLocalizationArtifactFindingCode
    action: PtmLocalizationArtifactFindingAction
    message: NonEmptyStr
    target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0505_MAX_TARGETS)
    detector_classes: tuple[PtmLocalizationArtifactDetectorClass, ...] = Field(
        default=(), max_length=M0505_DETECTOR_CLASS_COUNT
    )

    @model_validator(mode="after")
    def finding_is_closed(self) -> PtmLocalizationArtifactFinding:
        opaque_ptm_localization_artifact_identifier(self.finding_id, "finding.m0505")
        for target_id in self.target_ids:
            opaque_ptm_localization_artifact_identifier(target_id, "target")
        if self.action is not _ACTION_BY_FINDING[self.code]:
            raise ValueError("finding action contradicts its code")
        expected_message = self.code.value.replace("_", " ").capitalize() + "."
        if self.message != expected_message:
            raise ValueError("finding message contradicts its code")
        return self


class PtmLocalizationArtifactComputationReceipt(FrozenModel):
    quality_result_digest: Sha256Digest
    quality_contract_version: SemanticVersion
    quality_configuration_digest: Sha256Digest
    quality_receipt_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    raw_input_receipt_digest: Sha256Digest
    detector_policy_digest: Sha256Digest
    detector_configuration_digest: Sha256Digest
    selected_profile_digest: Sha256Digest | None
    evidence_ledger_digest: Sha256Digest | None
    event_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=M0505_MAX_EVENTS)
    posterior_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=M0505_MAX_EVENTS)
    contamination_flag_digests: tuple[Sha256Digest, ...] = Field(
        default=(), max_length=M0505_MAX_FLAGS
    )
    excluded_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0505_MAX_TARGETS)
    finding_codes: tuple[PtmLocalizationArtifactFindingCode, ...] = Field(
        default=(), max_length=M0505_MAX_FINDINGS
    )
    parent_target: Literal["variant_peptide"] = M0505_PARENT
    emits_parent: Literal[False] = False
    disposition: PtmLocalizationArtifactDisposition
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def receipt_is_closed(self) -> PtmLocalizationArtifactComputationReceipt:
        from glio_proteogen.contracts.m05_05.canonical import receipt_digest  # noqa: PLC0415

        if len(self.event_digests) != len(self.posterior_digests):
            raise ValueError("every traversed event requires one posterior")
        if self.evidence_ledger_digest is None and any(
            (self.event_digests, self.posterior_digests, self.contamination_flag_digests)
        ):
            raise ValueError("safe failure cannot claim traversed detector outputs")
        if self.receipt_digest != receipt_digest(self):
            raise ValueError("receipt digest does not bind its canonical payload")
        return self


class PtmLocalizationArtifactDetectionResult(FrozenModel):
    output_type: Literal["ptm_localization_artifact_contamination_assessment"] = (
        "ptm_localization_artifact_contamination_assessment"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0505_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    receipt_digest: Sha256Digest
    result_digest: Sha256Digest
    request: DetectPtmLocalizationArtifactsRequest
    receipt: PtmLocalizationArtifactComputationReceipt
    artifact_posteriors: tuple[PtmLocalizationArtifactPosterior, ...] = Field(
        default=(), max_length=M0505_MAX_EVENTS
    )
    contamination_flags: tuple[PtmLocalizationContaminationFlag, ...] = Field(
        default=(), max_length=M0505_MAX_FLAGS
    )
    exclusion_mask: tuple[PtmLocalizationExclusionMaskEntry, ...] = Field(
        default=(), max_length=M0505_MAX_TARGETS
    )
    findings: tuple[PtmLocalizationArtifactFinding, ...] = Field(
        default=(), max_length=M0505_MAX_FINDINGS
    )
    disposition: PtmLocalizationArtifactDisposition
    parent_target: Literal["variant_peptide"] = M0505_PARENT
    emits_variant_peptide: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    localizes_modification: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=8, max_length=M0505_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def result_is_closed(self) -> PtmLocalizationArtifactDetectionResult:  # noqa: PLR0912
        from glio_proteogen.contracts.m05_05.canonical import (  # noqa: PLC0415
            canonical_request_digest,
            configuration_digest,
            contamination_flag_digest,
            policy_digest,
            result_payload_digest,
        )

        opaque_ptm_localization_artifact_identifier(self.result_id, "result")
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest is stale")
        if self.policy_digest != policy_digest(self.request.policy):
            raise ValueError("result policy digest is stale")
        if self.configuration_digest != configuration_digest(self.request.policy):
            raise ValueError("result configuration digest is stale")
        if self.receipt_digest != self.receipt.receipt_digest:
            raise ValueError("result receipt digest is stale")
        if self.receipt.disposition is not self.disposition:
            raise ValueError("result disposition does not match its receipt")
        expected_receipt_bindings = (
            (self.receipt.quality_result_digest, self.request.quality_result_digest),
            (self.receipt.quality_contract_version, self.request.quality_contract_version),
            (self.receipt.quality_configuration_digest, self.request.quality_configuration_digest),
            (self.receipt.quality_receipt_digest, self.request.quality_receipt_digest),
            (self.receipt.identity_resolution_digest, self.request.identity_resolution_digest),
            (self.receipt.raw_input_receipt_digest, self.request.raw_input_receipt_digest),
            (self.receipt.detector_policy_digest, self.policy_digest),
            (self.receipt.detector_configuration_digest, self.configuration_digest),
            (
                self.receipt.evidence_ledger_digest,
                self.request.evidence_ledger.ledger_digest
                if self.request.evidence_ledger is not None
                else None,
            ),
            (self.receipt.finding_codes, tuple(item.code for item in self.findings)),
            (
                self.receipt.posterior_digests,
                tuple(item.posterior_digest for item in self.artifact_posteriors),
            ),
            (
                self.receipt.contamination_flag_digests,
                tuple(sorted(contamination_flag_digest(item) for item in self.contamination_flags)),
            ),
            (
                self.receipt.excluded_target_ids,
                tuple(item.target_id for item in self.exclusion_mask),
            ),
        )
        if any(actual != expected for actual, expected in expected_receipt_bindings):
            raise ValueError("result receipt does not bind the complete detector output")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not bind its canonical payload")
        posteriors = {item.posterior_digest: item for item in self.artifact_posteriors}
        flags = {item.flag_id: item for item in self.contamination_flags}
        if len(posteriors) != len(self.artifact_posteriors) or len(flags) != len(
            self.contamination_flags
        ):
            raise ValueError("output identifiers and digests must be unique")
        for flag in self.contamination_flags:
            posterior = posteriors.get(flag.posterior_digest)
            if posterior is None or posterior.target_id != flag.target_id:
                raise ValueError("contamination flag must bind one emitted posterior")
        for entry in self.exclusion_mask:
            if any(digest not in posteriors for digest in entry.triggering_posterior_digests):
                raise ValueError("exclusion mask references an unknown posterior")
            if any(flag_id not in flags for flag_id in entry.triggering_flag_ids):
                raise ValueError("exclusion mask references an unknown contamination flag")
        if self.human_review_required != (
            self.disposition is not PtmLocalizationArtifactDisposition.CLEARED
        ):
            raise ValueError("human-review state contradicts detector disposition")
        if len(canonical_json_bytes(self)) > M0505_MAX_CANONICAL_RESULT_BYTES:
            raise ValueError("canonical M05-05 result exceeds the installed ceiling")
        return self


def finding_identifier(
    code: PtmLocalizationArtifactFindingCode,
    target_ids: tuple[Identifier, ...],
    detector_classes: tuple[PtmLocalizationArtifactDetectorClass, ...],
) -> Identifier:
    digest = sha256_digest(
        {
            "module_id": M0505_MODULE_ID,
            "code": code,
            "target_ids": tuple(sorted(target_ids)),
            "detector_classes": tuple(sorted(detector_classes)),
        }
    ).removeprefix("sha256:")
    return f"finding.m0505.{digest}"


__all__ = [name for name in globals() if name.startswith("M0505_")] + [
    "DetectPtmLocalizationArtifactsRequest",
    "PtmLocalizationArtifactComputationReceipt",
    "PtmLocalizationArtifactDetectionResult",
    "PtmLocalizationArtifactDetectorClass",
    "PtmLocalizationArtifactDisposition",
    "PtmLocalizationArtifactEvidenceEvent",
    "PtmLocalizationArtifactEvidenceLedger",
    "PtmLocalizationArtifactEvidenceLedgerBinding",
    "PtmLocalizationArtifactFinding",
    "PtmLocalizationArtifactFindingAction",
    "PtmLocalizationArtifactFindingCode",
    "PtmLocalizationArtifactObservationState",
    "PtmLocalizationArtifactPolicy",
    "PtmLocalizationArtifactPosterior",
    "PtmLocalizationArtifactPosteriorState",
    "PtmLocalizationArtifactProfile",
    "PtmLocalizationArtifactSeverity",
    "PtmLocalizationArtifactThreshold",
    "PtmLocalizationArtifactUpstreamDisposition",
    "PtmLocalizationContaminationFlag",
    "PtmLocalizationEvidenceUnitKind",
    "PtmLocalizationExclusionMaskEntry",
    "PtmLocalizationExclusionReasonCode",
    "finding_identifier",
    "opaque_ptm_localization_artifact_identifier",
]
