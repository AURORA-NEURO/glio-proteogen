"""Strict public contracts for M02-05 identification-artifact detection."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from glio_proteogen.contracts.m01_05 import (
    ArtifactClass,
    ArtifactRule,
    Comparison,
    DetectionDisposition,
    ExclusionMask,
    FlagDisposition,
    FlagProvenance,
    PosteriorEstimate,
    PosteriorState,
)
from glio_proteogen.contracts.m02_05.canonical import (
    configuration_digest,
    configuration_manifest_digest,
    policy_digest,
    profile_digest,
    result_payload_digest,
    rule_digest,
    signal_summary_digest_from_values,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
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
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0205_MODULE_ID: Final = "GLIO-PROTEOGEN-M02-05"
M0205_CONTRACT_VERSION: Final = "1.0.0"
M0205_MAX_RULES: Final = 256
M0205_MAX_SIGNALS: Final = 10_000
M0205_MAX_FLAGS: Final = 10_000
M0205_MAX_EVALUATIONS: Final = 20_000
M0205_MAX_EVIDENCE_PER_SIGNAL: Final = 64
M0205_MAX_PROVENANCE_INPUTS: Final = 10_000
M0205_TOP_EVIDENCE_COUNT: Final = 8
M0205_ARTIFACT_LIMITATION_CODE: Final = "identification_artifact_detection_only"
M0205_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)

SignalUnit = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9%][A-Za-z0-9%._/*^-]*$"),
]


class IdentificationSignalState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class IdentificationArtifactProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    required_rule_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0205_MAX_RULES)
    evidence: ArtifactReference

    @field_validator("required_rule_ids")
    @classmethod
    def required_rules_are_unique(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("identification detector profile rule identifiers must be unique")
        return values


class IdentificationArtifactPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    review_threshold: float = Field(ge=0.0, le=1.0)
    exclusion_threshold: float = Field(ge=0.0, le=1.0)
    enabled_classes: tuple[ArtifactClass, ...] = Field(
        default_factory=lambda: tuple(ArtifactClass),
        min_length=1,
        max_length=len(ArtifactClass),
    )
    max_rules: int = Field(default=M0205_MAX_RULES, gt=0, le=M0205_MAX_RULES)
    max_signals: int = Field(default=M0205_MAX_SIGNALS, gt=0, le=M0205_MAX_SIGNALS)
    max_flags: int = Field(default=M0205_MAX_FLAGS, gt=0, le=M0205_MAX_FLAGS)
    max_evaluations: int = Field(
        default=M0205_MAX_EVALUATIONS,
        gt=0,
        le=M0205_MAX_EVALUATIONS,
    )

    @field_validator("enabled_classes")
    @classmethod
    def enabled_classes_are_unique(
        cls,
        values: tuple[ArtifactClass, ...],
    ) -> tuple[ArtifactClass, ...]:
        if len(values) != len(set(values)):
            raise ValueError("enabled identification artifact classes must be unique")
        return values

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> IdentificationArtifactPolicy:
        if self.review_threshold >= self.exclusion_threshold:
            raise ValueError("review threshold must be below exclusion threshold")
        return self


class IdentificationSignalObservation(FrozenModel):
    target_id: Identifier
    signal_id: Identifier
    state: IdentificationSignalState
    value: float | bool | None = None
    unit: SignalUnit | None = None
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0205_MAX_EVIDENCE_PER_SIGNAL,
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        values: tuple[ArtifactReference, ...],
    ) -> tuple[ArtifactReference, ...]:
        if len(values) != len(set(values)):
            raise ValueError("identification signal evidence references must be unique")
        if len(values) != len({item.digest for item in values}):
            raise ValueError("identification signal evidence digests must be unique")
        return values

    @model_validator(mode="after")
    def value_matches_state(self) -> IdentificationSignalObservation:
        if self.state is IdentificationSignalState.OBSERVED and self.value is None:
            raise ValueError("observed identification signal requires a value")
        if self.state is not IdentificationSignalState.OBSERVED and self.value is not None:
            raise ValueError("non-observed identification signal cannot carry a value")
        if self.state is not IdentificationSignalState.OBSERVED and self.unit is not None:
            raise ValueError("non-observed identification signal cannot carry a unit")
        return self


class DetectIdentificationArtifactsRequest(FrozenModel):
    operation: Literal["detect_identification_artifacts"] = "detect_identification_artifacts"
    contract_version: Literal["1.0.0"] = M0205_CONTRACT_VERSION
    context: ExecutionContext
    detector_profile: IdentificationArtifactProfile
    policy: IdentificationArtifactPolicy
    rules: tuple[ArtifactRule, ...] = Field(min_length=1, max_length=M0205_MAX_RULES)
    signals: tuple[IdentificationSignalObservation, ...] = Field(
        min_length=1,
        max_length=M0205_MAX_SIGNALS,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_closed_and_bound(  # noqa: PLR0912
        self,
    ) -> DetectIdentificationArtifactsRequest:
        _require_authorized_context(self.context)
        if len(self.rules) != len({item.rule_id for item in self.rules}):
            raise ValueError("identification artifact rule identifiers must be unique")
        signal_keys = [(item.target_id, item.signal_id) for item in self.signals]
        if len(signal_keys) != len(set(signal_keys)):
            raise ValueError("identification signal target/identifier pairs must be unique")
        if len(self.rules) > self.policy.max_rules or len(self.signals) > self.policy.max_signals:
            raise ValueError("identification artifact request exceeds the active policy")
        rule_map = {item.rule_id: item for item in self.rules}
        if not set(self.detector_profile.required_rule_ids).issubset(rule_map):
            raise ValueError("identification detector profile references an undefined rule")
        if any(item.artifact_class not in self.policy.enabled_classes for item in self.rules):
            raise ValueError("identification artifact rule class is disabled")
        if any(item.posterior_if_clear >= self.policy.review_threshold for item in self.rules):
            raise ValueError("clear configured posterior must remain below review threshold")
        signal_ids = {item.signal_id for item in self.signals}
        if any(item.signal_id not in signal_ids for item in self.rules):
            raise ValueError("identification artifact rule references an unknown signal")
        configured_signal_ids = {item.signal_id for item in self.rules}
        if not signal_ids.issubset(configured_signal_ids):
            raise ValueError("identification signal is not covered by the active rules")
        _validate_observation_compatibility(self.rules, self.signals)
        target_count = len({item.target_id for item in self.signals})
        class_count = len({item.artifact_class for item in self.rules})
        if target_count * class_count > self.policy.max_flags:
            raise ValueError("identification artifact request exceeds the result flag limit")
        if target_count * len(self.rules) > self.policy.max_evaluations:
            raise ValueError("identification artifact request exceeds evaluation trace capacity")
        if len(self.rules) + 11 > M0205_MAX_PROVENANCE_INPUTS:
            raise ValueError("identification artifact request exceeds provenance capacity")
        _require_flag_evidence_capacity(self)
        expected = configuration_digest(self.detector_profile, self.policy, self.rules)
        if self.context.references.approved_configuration.evidence.digest != expected:
            raise ValueError("approved configuration does not bind identification detector")
        top_evidence = {
            self.detector_profile.evidence.digest,
            self.context.references.approved_configuration.evidence.digest,
            self.context.references.identity_lineage.evidence.digest,
            self.context.references.provenance.evidence.digest,
            self.context.references.consent.evidence.digest,
            self.context.references.quality.evidence.digest,
            self.context.references.support.evidence.digest,
            self.context.references.intended_use.evidence.digest,
        }
        if len(top_evidence) != M0205_TOP_EVIDENCE_COUNT:
            raise ValueError("profile and control evidence digests must be distinct")
        return self


class RuleEvaluationTrace(FrozenModel):
    target_id: Identifier
    rule_id: Identifier
    artifact_class: ArtifactClass
    signal_id: Identifier
    rule_digest: Sha256Digest
    rule: ArtifactRule
    signal_digest: Sha256Digest | None = None
    signal_state: IdentificationSignalState | None = None
    signal_value: float | bool | None = None
    signal_unit: SignalUnit | None = None
    evidence_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=64)
    triggered: bool = False
    posterior_if_triggered: float = Field(ge=0.0, le=1.0)
    posterior_if_clear: float = Field(ge=0.0, le=1.0)
    required_signal: bool
    exclusion_eligible: bool

    @model_validator(mode="after")
    def trace_is_closed(self) -> RuleEvaluationTrace:
        if (
            self.rule_id != self.rule.rule_id
            or self.artifact_class is not self.rule.artifact_class
            or self.signal_id != self.rule.signal_id
            or self.rule_digest != rule_digest(self.rule)
            or self.posterior_if_triggered != self.rule.posterior_if_triggered
            or self.posterior_if_clear != self.rule.posterior_if_clear
            or self.required_signal is not self.rule.required_signal
            or self.exclusion_eligible is not self.rule.exclusion_eligible
        ):
            raise ValueError("rule evaluation trace contradicts its exact rule")
        if len(self.evidence_digests) != len(set(self.evidence_digests)):
            raise ValueError("rule evaluation evidence digests must be unique")
        has_signal = self.signal_digest is not None
        if has_signal != (self.signal_state is not None) or has_signal != bool(
            self.evidence_digests
        ):
            raise ValueError("rule evaluation signal trace must be all present or all absent")
        if self.triggered and self.signal_state is not IdentificationSignalState.OBSERVED:
            raise ValueError("only an observed signal can trigger an artifact rule")
        if self.signal_state is IdentificationSignalState.OBSERVED:
            if self.signal_value is None:
                raise ValueError("observed rule trace requires a signal value")
            is_boolean = self.rule.comparison is Comparison.BOOLEAN_EQUAL
            if is_boolean and (
                not isinstance(self.signal_value, bool) or self.signal_unit is not None
            ):
                raise ValueError("boolean rule trace requires a unitless boolean")
            if not is_boolean and (
                isinstance(self.signal_value, bool) or self.signal_unit != self.rule.unit
            ):
                raise ValueError("numeric rule trace unit contradicts its rule")
        elif self.signal_value is not None or self.signal_unit is not None:
            raise ValueError("non-observed rule trace cannot carry a value or unit")
        if self.signal_digest is not None and signal_summary_digest_from_values(
            (
                self.target_id,
                self.signal_id,
                _present_signal_state(self.signal_state).value,
                self.signal_value,
                self.signal_unit,
            ),
            self.evidence_digests,
        ) != self.signal_digest:
            raise ValueError("rule trace signal digest contradicts its aggregate summary")
        if self.triggered is not _rule_triggered(
            self.rule,
            self.signal_state,
            value=self.signal_value,
        ):
            raise ValueError("rule trace trigger contradicts rule and aggregate signal")
        if self.posterior_if_triggered < self.posterior_if_clear:
            raise ValueError("triggered posterior cannot be below clear posterior")
        return self


class IdentificationArtifactFlag(FrozenModel):
    target_id: Identifier
    artifact_class: ArtifactClass
    posterior: PosteriorEstimate
    disposition: FlagDisposition
    rule_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0205_MAX_RULES)
    evaluations: tuple[RuleEvaluationTrace, ...] = Field(
        min_length=1,
        max_length=M0205_MAX_RULES,
    )
    provenance: FlagProvenance
    evidence: tuple[ArtifactReference, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def flag_is_self_consistent(self) -> IdentificationArtifactFlag:
        if len(self.rule_ids) != len(set(self.rule_ids)) or set(self.rule_ids) != {
            item.rule_id for item in self.evaluations
        }:
            raise ValueError("artifact flag rules contradict evaluation traces")
        if any(item.artifact_class is not self.artifact_class for item in self.evaluations):
            raise ValueError("artifact flag class contradicts evaluation traces")
        if any(item.target_id != self.target_id for item in self.evaluations):
            raise ValueError("artifact flag target contradicts evaluation traces")
        if len(self.evaluations) != len({item.rule_id for item in self.evaluations}):
            raise ValueError("artifact flag evaluation traces must be unique")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("artifact flag evidence must be unique")
        if len(self.evidence) != len({item.digest for item in self.evidence}):
            raise ValueError("artifact flag evidence digests must be unique")
        expected_rule_digests = {item.rule_digest for item in self.evaluations}
        expected_signal_digests = {
            item.signal_digest for item in self.evaluations if item.signal_digest is not None
        }
        if set(self.provenance.rule_digests) != expected_rule_digests or set(
            self.provenance.signal_digests
        ) != expected_signal_digests:
            raise ValueError("artifact flag provenance contradicts evaluation traces")
        evidence_digests = {item.digest for item in self.evidence}
        traced_evidence = {
            digest for item in self.evaluations for digest in item.evidence_digests
        }
        if not traced_evidence.issubset(evidence_digests):
            raise ValueError("artifact flag evidence does not cover its signal traces")
        if (self.posterior.state is PosteriorState.NOT_EVALUABLE) != (
            self.disposition is FlagDisposition.NOT_EVALUABLE
        ):
            raise ValueError("artifact flag posterior state contradicts its disposition")
        return self


class IdentificationArtifactDetectionResult(FrozenModel):
    output_type: Literal["identification_artifact_detection_result"] = (
        "identification_artifact_detection_result"
    )
    detection_id: Identifier
    result_version: Literal["1.0.0"] = M0205_CONTRACT_VERSION
    request_digest: Sha256Digest
    profile_id: Identifier
    profile_version: SemanticVersion
    profile_digest: Sha256Digest
    profile_evidence_digest: Sha256Digest
    required_rule_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0205_MAX_RULES,
    )
    policy_id: Identifier
    policy_version: SemanticVersion
    policy_digest: Sha256Digest
    enabled_classes: tuple[ArtifactClass, ...] = Field(
        min_length=1,
        max_length=len(ArtifactClass),
    )
    max_rules: int = Field(gt=0, le=M0205_MAX_RULES)
    max_signals: int = Field(gt=0, le=M0205_MAX_SIGNALS)
    max_flags: int = Field(gt=0, le=M0205_MAX_FLAGS)
    max_evaluations: int = Field(gt=0, le=M0205_MAX_EVALUATIONS)
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: DetectionDisposition
    review_threshold: float = Field(ge=0.0, le=1.0)
    exclusion_threshold: float = Field(ge=0.0, le=1.0)
    evaluated_target_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0205_MAX_FLAGS,
    )
    flags: tuple[IdentificationArtifactFlag, ...] = Field(
        min_length=1,
        max_length=M0205_MAX_FLAGS,
    )
    exclusion_mask: ExclusionMask
    parent_target: Literal["protein_subtype"] = "protein_subtype"
    mask_scope: Literal["identification_evidence"] = "identification_evidence"
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=8, max_length=8)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def result_is_relationally_closed(  # noqa: PLR0912, PLR0915
        self,
    ) -> IdentificationArtifactDetectionResult:
        if len(self.required_rule_ids) != len(set(self.required_rule_ids)):
            raise ValueError("result required rule identifiers must be unique")
        if len(self.enabled_classes) != len(set(self.enabled_classes)):
            raise ValueError("result enabled artifact classes must be unique")
        if len(self.evaluated_target_ids) != len(set(self.evaluated_target_ids)):
            raise ValueError("evaluated target identifiers must be unique")
        keys = [(item.target_id, item.artifact_class) for item in self.flags]
        if len(keys) != len(set(keys)):
            raise ValueError("identification artifact flags must be unique")
        if self.review_threshold >= self.exclusion_threshold:
            raise ValueError("result thresholds are not ordered")
        reconstructed_policy = IdentificationArtifactPolicy(
            policy_id=self.policy_id,
            version=self.policy_version,
            review_threshold=self.review_threshold,
            exclusion_threshold=self.exclusion_threshold,
            enabled_classes=self.enabled_classes,
            max_rules=self.max_rules,
            max_signals=self.max_signals,
            max_flags=self.max_flags,
            max_evaluations=self.max_evaluations,
        )
        if policy_digest(reconstructed_policy) != self.policy_digest:
            raise ValueError("result policy manifest does not match its digest")
        signal_summaries: dict[tuple[Identifier, Identifier], tuple[object, ...]] = {}
        rule_summaries: dict[Identifier, Sha256Digest] = {}
        rules_by_class: dict[ArtifactClass, set[tuple[Identifier, Sha256Digest]]] = {}
        for flag in self.flags:
            for trace in flag.evaluations:
                signal_key = (trace.target_id, trace.signal_id)
                signal_summary = (
                    trace.signal_digest,
                    trace.signal_state,
                    trace.signal_value,
                    trace.signal_unit,
                    trace.evidence_digests,
                )
                prior_signal = signal_summaries.setdefault(signal_key, signal_summary)
                if prior_signal != signal_summary:
                    raise ValueError("reused signal traces must carry one identical summary")
                prior_rule = rule_summaries.setdefault(trace.rule_id, trace.rule_digest)
                if prior_rule != trace.rule_digest:
                    raise ValueError("reused rule identifiers must carry one exact rule")
                rules_by_class.setdefault(trace.artifact_class, set()).add(
                    (trace.rule_id, trace.rule_digest)
                )
        for flag in self.flags:
            flag_rules = {
                (trace.rule_id, trace.rule_digest) for trace in flag.evaluations
            }
            if flag_rules != rules_by_class[flag.artifact_class]:
                raise ValueError("every class flag must evaluate the complete configured rule set")
        exact_rules = {
            item.rule.rule_id: item.rule
            for flag in self.flags
            for item in flag.evaluations
        }
        if not set(self.required_rule_ids).issubset(exact_rules):
            raise ValueError("result omits a required detector rule")
        if any(
            item.posterior_if_clear >= self.review_threshold
            or item.artifact_class not in self.enabled_classes
            for item in exact_rules.values()
        ):
            raise ValueError("result rules contradict the active policy")
        configured_classes = {item.artifact_class for item in exact_rules.values()}
        expected_flag_keys = {
            (target_id, artifact_class)
            for target_id in self.evaluated_target_ids
            for artifact_class in configured_classes
        }
        if set(keys) != expected_flag_keys:
            raise ValueError("result flags do not cover every evaluated target and class")
        if len(self.flags) > self.max_flags or len(self.flags) > M0205_MAX_FLAGS:
            raise ValueError("result exceeds its flag capacity")
        if sum(len(item.evaluations) for item in self.flags) > self.max_evaluations:
            raise ValueError("result exceeds its evaluation trace capacity")
        expected_config = configuration_manifest_digest(
            self.profile_digest,
            self.policy_digest,
            tuple(
                {
                    digest
                    for item in self.flags
                    for digest in item.provenance.rule_digests
                }
            ),
        )
        if self.configuration_digest != expected_config:
            raise ValueError("result configuration manifest is inconsistent")
        for flag in self.flags:
            if flag.provenance.configuration_digest != self.configuration_digest:
                raise ValueError("artifact flag uses a different configuration")
            expected_posterior, expected_flag_disposition = _trace_outcome(
                flag.evaluations,
                review_threshold=self.review_threshold,
                exclusion_threshold=self.exclusion_threshold,
            )
            if (
                flag.posterior != expected_posterior
                or flag.disposition is not expected_flag_disposition
            ):
                raise ValueError("artifact flag contradicts result thresholds")
        expected_excluded = {
            item.target_id for item in self.flags if item.disposition is FlagDisposition.EXCLUDE
        }
        expected_review = {
            item.target_id
            for item in self.flags
            if item.disposition in {FlagDisposition.REVIEW, FlagDisposition.NOT_EVALUABLE}
        } - expected_excluded
        if set(self.exclusion_mask.excluded_target_ids) != expected_excluded or set(
            self.exclusion_mask.review_target_ids
        ) != expected_review:
            raise ValueError("identification exclusion mask contradicts flags")
        expected_result_disposition = (
            DetectionDisposition.QUARANTINED
            if expected_excluded or expected_review
            else DetectionDisposition.ACCEPTED
        )
        if self.disposition is not expected_result_disposition:
            raise ValueError("identification artifact disposition contradicts flags")
        _validate_result_envelope(self)
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("identification artifact result digest does not match content")
        return self


def _trace_outcome(
    evaluations: tuple[RuleEvaluationTrace, ...],
    *,
    review_threshold: float = 0.5,
    exclusion_threshold: float = 0.9,
) -> tuple[PosteriorEstimate, FlagDisposition]:
    observed = [
        item
        for item in evaluations
        if item.signal_state is IdentificationSignalState.OBSERVED
    ]
    indeterminate = not observed or any(
        item.signal_state is IdentificationSignalState.UNSUPPORTED
        or (item.required_signal and item.signal_state is not IdentificationSignalState.OBSERVED)
        for item in evaluations
    )
    if indeterminate:
        return (
            PosteriorEstimate(state=PosteriorState.NOT_EVALUABLE),
            FlagDisposition.NOT_EVALUABLE,
        )
    triggered = [item for item in evaluations if item.triggered]
    posterior_value = (
        max(item.posterior_if_triggered for item in triggered)
        if triggered
        else max(item.posterior_if_clear for item in evaluations)
    )
    maximum_sources = [
        item for item in triggered if item.posterior_if_triggered == posterior_value
    ]
    can_exclude = bool(maximum_sources) and all(
        item.exclusion_eligible for item in maximum_sources
    )
    disposition = (
        FlagDisposition.EXCLUDE
        if can_exclude and posterior_value >= exclusion_threshold
        else FlagDisposition.REVIEW
        if posterior_value >= review_threshold
        else FlagDisposition.CLEAR
    )
    return PosteriorEstimate(state=PosteriorState.ESTIMATED, value=posterior_value), disposition


def _rule_triggered(  # noqa: PLR0911 - closed comparison union.
    rule: ArtifactRule,
    state: IdentificationSignalState | None,
    *,
    value: float | bool | None,
) -> bool:
    if state is not IdentificationSignalState.OBSERVED or value is None:
        return False
    if rule.comparison is Comparison.BOOLEAN_EQUAL:
        return isinstance(value, bool) and value is rule.expected_bool
    if isinstance(value, bool) or rule.threshold is None:
        return False
    if rule.comparison is Comparison.GREATER_THAN_OR_EQUAL:
        return value >= rule.threshold
    if rule.comparison is Comparison.LESS_THAN_OR_EQUAL:
        return value <= rule.threshold
    if rule.upper_threshold is None:
        return False
    within = rule.threshold <= value <= rule.upper_threshold
    return within if rule.comparison is Comparison.WITHIN_RANGE else not within


def _present_signal_state(
    state: IdentificationSignalState | None,
) -> IdentificationSignalState:
    if state is None:
        raise ValueError("signal trace requires a state")
    return state


def _validate_observation_compatibility(
    rules: tuple[ArtifactRule, ...],
    signals: tuple[IdentificationSignalObservation, ...],
) -> None:
    by_id: dict[Identifier, list[IdentificationSignalObservation]] = {}
    for signal in signals:
        by_id.setdefault(signal.signal_id, []).append(signal)
    for rule in rules:
        for signal in by_id.get(rule.signal_id, []):
            if signal.state is not IdentificationSignalState.OBSERVED:
                continue
            is_boolean = rule.comparison is Comparison.BOOLEAN_EQUAL
            if is_boolean and (not isinstance(signal.value, bool) or signal.unit is not None):
                raise ValueError("boolean identification signals must be unitless booleans")
            if not is_boolean and (isinstance(signal.value, bool) or signal.unit != rule.unit):
                raise ValueError("numeric identification signal unit must match its rule")


def _validate_result_envelope(result: IdentificationArtifactDetectionResult) -> None:
    expected_support = {
        DetectionDisposition.ACCEPTED: (
            SupportStatus.LIMITED,
            "identification_artifact_screen_clear",
            False,
        ),
        DetectionDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "identification_artifact_screen_quarantined",
            True,
        ),
    }[result.disposition]
    if (
        result.support.status,
        result.support.reason_code,
        result.human_review_required,
    ) != expected_support:
        raise ValueError("identification artifact support contradicts disposition")
    suffix = result.request_digest.removeprefix("sha256:")
    provenance = result.provenance
    if (
        result.detection_id != f"detection.m0205.{suffix}"
        or provenance.activity_id != f"activity.m0205.{suffix}"
        or provenance.module_id != M0205_MODULE_ID
        or provenance.module_version != result.result_version
        or provenance.generated_at != result.completed_at
        or provenance.configuration_digest != result.configuration_digest
    ):
        raise ValueError("identification artifact provenance is inconsistent")
    required = {
        result.request_digest,
        result.profile_digest,
        result.profile_evidence_digest,
        result.policy_digest,
        result.configuration_digest,
        *(digest for flag in result.flags for digest in flag.provenance.rule_digests),
        *(item.evidence_digest for item in provenance.control_decisions),
    }
    if not required.issubset(provenance.input_digests):
        raise ValueError("identification artifact provenance inputs are incomplete")
    expected_states = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    controls = {item.role.value: item for item in provenance.control_decisions}
    if {key: value.state for key, value in controls.items()} != expected_states:
        raise ValueError("identification artifact control states are inconsistent")
    consent = controls["consent"]
    if (
        provenance.consent_decision_id,
        provenance.consent_state.value,
        provenance.consent_policy_version,
        provenance.consent_evidence_digest,
    ) != (
        consent.decision_id,
        consent.state,
        consent.policy_version,
        consent.evidence_digest,
    ):
        raise ValueError("identification artifact consent provenance is inconsistent")
    if controls["approved_configuration"].evidence_digest != result.configuration_digest:
        raise ValueError("approved configuration does not bind result")
    if {item.code for item in result.limitations} != {
        M0205_ARTIFACT_LIMITATION_CODE,
        M0205_AUTHORITY_LIMITATION_CODE,
    }:
        raise ValueError("identification artifact result requires both limitations")
    if len(result.evidence) != len(set(result.evidence)):
        raise ValueError("identification artifact evidence must be unique")
    if len(result.evidence) != len({item.reference.digest for item in result.evidence}):
        raise ValueError("identification artifact evidence digests must be unique")
    expected_evidence_digests = {
        result.profile_evidence_digest,
        *(item.evidence_digest for item in provenance.control_decisions),
    }
    if {item.reference.digest for item in result.evidence} != expected_evidence_digests:
        raise ValueError("identification artifact evidence index is inconsistent")
    profile_reference = next(
        item.reference
        for item in result.evidence
        if item.reference.digest == result.profile_evidence_digest
    )
    reconstructed_profile = IdentificationArtifactProfile(
        profile_id=result.profile_id,
        version=result.profile_version,
        required_rule_ids=result.required_rule_ids,
        evidence=profile_reference,
    )
    if profile_digest(reconstructed_profile) != result.profile_digest:
        raise ValueError("result profile manifest does not match its digest")
    expected_evidence_claims = {
        (
            item.evidence_digest,
            "evidence",
            f"Caller-declared {item.role.value} control; issuer is not authenticated.",
        )
        for item in provenance.control_decisions
    }
    expected_evidence_claims.add(
        (
            result.profile_evidence_digest,
            "evidence",
            "Caller-declared identification detector profile; issuer is not authenticated.",
        )
    )
    if {
        (item.reference.digest, item.role, item.claim) for item in result.evidence
    } != expected_evidence_claims:
        raise ValueError("identification artifact evidence claims are inconsistent")


def _require_flag_evidence_capacity(request: DetectIdentificationArtifactsRequest) -> None:
    signals = {(item.target_id, item.signal_id): item for item in request.signals}
    targets = {item.target_id for item in request.signals}
    by_class = {
        artifact_class: tuple(
            item for item in request.rules if item.artifact_class is artifact_class
        )
        for artifact_class in ArtifactClass
    }
    for target_id in targets:
        for rules in by_class.values():
            if not rules:
                continue
            references = {request.detector_profile.evidence}
            for rule in rules:
                signal = signals.get((target_id, rule.signal_id))
                if signal is not None:
                    references.update(signal.evidence)
            if len(references) > M0205_MAX_EVIDENCE_PER_SIGNAL:
                raise ValueError("identification artifact flag evidence exceeds output capacity")


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize identification artifact detection")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before artifact detection")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic):
        raise ValueError("every upstream control must accept artifact detection")


__all__ = [
    "M0205_ARTIFACT_LIMITATION_CODE",
    "M0205_AUTHORITY_LIMITATION_CODE",
    "M0205_CONTRACT_VERSION",
    "M0205_MAX_EVALUATIONS",
    "M0205_MAX_FLAGS",
    "M0205_MAX_RULES",
    "M0205_MAX_SIGNALS",
    "M0205_MODULE_ID",
    "ArtifactClass",
    "ArtifactRule",
    "Comparison",
    "DetectIdentificationArtifactsRequest",
    "DetectionDisposition",
    "ExclusionMask",
    "FlagDisposition",
    "FlagProvenance",
    "IdentificationArtifactDetectionResult",
    "IdentificationArtifactFlag",
    "IdentificationArtifactPolicy",
    "IdentificationArtifactProfile",
    "IdentificationSignalObservation",
    "IdentificationSignalState",
    "PosteriorEstimate",
    "PosteriorState",
    "RuleEvaluationTrace",
]
