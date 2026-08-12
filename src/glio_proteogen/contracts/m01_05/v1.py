"""Strict public contracts for deterministic M01-05 artifact detection."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from glio_proteogen.contracts.m01_05.canonical import (
    configuration_digest,
    result_payload_digest,
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

M0105_MODULE_ID: Final = "GLIO-PROTEOGEN-M01-05"
M0105_CONTRACT_VERSION: Final = "1.0.0"
M0105_MAX_RULES: Final = 256
M0105_MAX_SIGNALS: Final = 10_000
M0105_MAX_FLAGS: Final = 10_000
M0105_MAX_EVIDENCE_PER_ITEM: Final = 64
M0105_MAX_PROVENANCE_INPUTS: Final = 10_000
M0105_ARTIFACT_LIMITATION_CODE: Final = "artifact_detection_only"
M0105_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)

SignalUnit = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9%][A-Za-z0-9%._/*^-]*$"),
]


class ArtifactClass(StrEnum):
    TECHNICAL = "technical"
    CONTAMINATION = "contamination"
    BARCODE_INDEX = "barcode_index"
    BATCH = "batch"
    LOW_COMPLEXITY = "low_complexity"
    MAPPING = "mapping"
    CONTEXT_FALSE_POSITIVE = "context_false_positive"


class SignalState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class Comparison(StrEnum):
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    WITHIN_RANGE = "within_range"
    OUTSIDE_RANGE = "outside_range"
    BOOLEAN_EQUAL = "boolean_equal"


class PosteriorState(StrEnum):
    ESTIMATED = "estimated"
    NOT_EVALUABLE = "not_evaluable"


class FlagDisposition(StrEnum):
    CLEAR = "clear"
    REVIEW = "review"
    EXCLUDE = "exclude"
    NOT_EVALUABLE = "not_evaluable"


class DetectionDisposition(StrEnum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"


class DetectorProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    required_rule_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0105_MAX_RULES)
    evidence: ArtifactReference

    @field_validator("required_rule_ids")
    @classmethod
    def required_rules_are_unique(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("detector profile rule identifiers must be unique")
        return values


class ArtifactRule(FrozenModel):
    rule_id: Identifier
    version: SemanticVersion
    artifact_class: ArtifactClass
    signal_id: Identifier
    comparison: Comparison
    threshold: float | None = None
    upper_threshold: float | None = None
    expected_bool: bool | None = None
    unit: SignalUnit | None = None
    posterior_if_triggered: float = Field(ge=0.0, le=1.0)
    posterior_if_clear: float = Field(ge=0.0, le=1.0)
    required_signal: bool = True
    exclusion_eligible: bool = True

    @model_validator(mode="after")
    def rule_parameters_are_closed(self) -> ArtifactRule:
        is_boolean = self.comparison is Comparison.BOOLEAN_EQUAL
        if is_boolean != (self.expected_bool is not None):
            raise ValueError("boolean comparison requires only an expected boolean")
        if is_boolean and (self.threshold is not None or self.upper_threshold is not None):
            raise ValueError("boolean comparison cannot carry numeric thresholds")
        if is_boolean and self.unit is not None:
            raise ValueError("boolean artifact rules must be unitless")
        if not is_boolean and self.threshold is None:
            raise ValueError("numeric comparison requires a threshold")
        if not is_boolean and self.unit is None:
            raise ValueError("numeric artifact rules require a unit")
        needs_upper = self.comparison in {Comparison.WITHIN_RANGE, Comparison.OUTSIDE_RANGE}
        if needs_upper != (self.upper_threshold is not None):
            raise ValueError("range comparison requires exactly two thresholds")
        if (
            self.threshold is not None
            and self.upper_threshold is not None
            and self.threshold > self.upper_threshold
        ):
            raise ValueError("artifact rule lower threshold cannot exceed upper threshold")
        if self.posterior_if_triggered < self.posterior_if_clear:
            raise ValueError("triggered posterior cannot be below the clear posterior")
        return self


class SignalObservation(FrozenModel):
    target_id: Identifier
    signal_id: Identifier
    state: SignalState
    value: float | bool | None = None
    unit: SignalUnit | None = None
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0105_MAX_EVIDENCE_PER_ITEM,
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        values: tuple[ArtifactReference, ...],
    ) -> tuple[ArtifactReference, ...]:
        if len(values) != len(set(values)):
            raise ValueError("signal evidence references must be unique")
        return values

    @model_validator(mode="after")
    def value_matches_state(self) -> SignalObservation:
        if self.state is SignalState.OBSERVED and self.value is None:
            raise ValueError("observed artifact signal requires a value")
        if self.state is not SignalState.OBSERVED and self.value is not None:
            raise ValueError("non-observed artifact signal cannot carry a value")
        return self


class ArtifactDetectionPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    review_threshold: float = Field(ge=0.0, le=1.0)
    exclusion_threshold: float = Field(ge=0.0, le=1.0)
    enabled_classes: tuple[ArtifactClass, ...] = Field(
        min_length=1,
        max_length=len(ArtifactClass),
    )
    max_rules: int = Field(default=M0105_MAX_RULES, gt=0, le=M0105_MAX_RULES)
    max_signals: int = Field(default=M0105_MAX_SIGNALS, gt=0, le=M0105_MAX_SIGNALS)

    @field_validator("enabled_classes")
    @classmethod
    def enabled_classes_are_unique(
        cls,
        values: tuple[ArtifactClass, ...],
    ) -> tuple[ArtifactClass, ...]:
        if len(values) != len(set(values)):
            raise ValueError("enabled artifact classes must be unique")
        return values

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> ArtifactDetectionPolicy:
        if self.review_threshold >= self.exclusion_threshold:
            raise ValueError("review threshold must be below the exclusion threshold")
        return self


class DetectArtifactsRequest(FrozenModel):
    operation: Literal["detect_artifacts"] = "detect_artifacts"
    contract_version: Literal["1.0.0"] = M0105_CONTRACT_VERSION
    context: ExecutionContext
    detector_profile: DetectorProfile
    policy: ArtifactDetectionPolicy
    rules: tuple[ArtifactRule, ...] = Field(min_length=1, max_length=M0105_MAX_RULES)
    signals: tuple[SignalObservation, ...] = Field(min_length=1, max_length=M0105_MAX_SIGNALS)
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_closed_and_configuration_bound(self) -> DetectArtifactsRequest:
        _require_authorized_context(self.context)
        _require_unique(self.rules, "rule_id", "artifact rule")
        signal_keys = [(signal.target_id, signal.signal_id) for signal in self.signals]
        if len(signal_keys) != len(set(signal_keys)):
            raise ValueError("artifact signal target/identifier pairs must be unique")
        if len(self.rules) > self.policy.max_rules or len(self.signals) > self.policy.max_signals:
            raise ValueError("artifact request exceeds the active policy")
        _require_representable_request(self)
        rule_map = {rule.rule_id: rule for rule in self.rules}
        if not set(self.detector_profile.required_rule_ids).issubset(rule_map):
            raise ValueError("detector profile references an undefined required rule")
        if any(rule.artifact_class not in self.policy.enabled_classes for rule in self.rules):
            raise ValueError("artifact rule class is disabled by the active policy")
        signal_ids = {signal.signal_id for signal in self.signals}
        if any(rule.signal_id not in signal_ids for rule in self.rules):
            raise ValueError("artifact rule references an unknown signal")
        signals_by_id: dict[Identifier, list[SignalObservation]] = {}
        for signal in self.signals:
            signals_by_id.setdefault(signal.signal_id, []).append(signal)
        for rule in self.rules:
            for signal in signals_by_id[rule.signal_id]:
                if signal.state is not SignalState.OBSERVED:
                    continue
                is_boolean = rule.comparison is Comparison.BOOLEAN_EQUAL
                if is_boolean and (
                    not isinstance(signal.value, bool) or signal.unit is not None
                ):
                    raise ValueError("boolean artifact signals must be boolean and unitless")
                if not is_boolean and (
                    isinstance(signal.value, bool) or signal.unit != rule.unit
                ):
                    raise ValueError("numeric artifact signal unit must match its rule")
        expected_configuration = configuration_digest(
            self.detector_profile,
            self.policy,
            self.rules,
        )
        if self.context.references.approved_configuration.evidence.digest != expected_configuration:
            raise ValueError("approved configuration does not bind the artifact detector")
        return self


class PosteriorEstimate(FrozenModel):
    state: PosteriorState
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    method: Literal["configured_rule_max"] = "configured_rule_max"

    @model_validator(mode="after")
    def value_matches_state(self) -> PosteriorEstimate:
        if self.state is PosteriorState.ESTIMATED and self.value is None:
            raise ValueError("estimated artifact posterior requires a value")
        if self.state is not PosteriorState.ESTIMATED and self.value is not None:
            raise ValueError("non-evaluable artifact posterior cannot carry a value")
        return self


class FlagProvenance(FrozenModel):
    configuration_digest: Sha256Digest
    rule_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=M0105_MAX_RULES)
    signal_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=M0105_MAX_RULES)

    @model_validator(mode="after")
    def digests_are_unique(self) -> FlagProvenance:
        if len(self.rule_digests) != len(set(self.rule_digests)):
            raise ValueError("flag rule digests must be unique")
        if len(self.signal_digests) != len(set(self.signal_digests)):
            raise ValueError("flag signal digests must be unique")
        return self


class ArtifactFlag(FrozenModel):
    target_id: Identifier
    artifact_class: ArtifactClass
    posterior: PosteriorEstimate
    disposition: FlagDisposition
    rule_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0105_MAX_RULES)
    provenance: FlagProvenance
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0105_MAX_EVIDENCE_PER_ITEM,
    )

    @model_validator(mode="after")
    def disposition_matches_posterior(self) -> ArtifactFlag:
        if len(self.rule_ids) != len(set(self.rule_ids)):
            raise ValueError("artifact flag rule identifiers must be unique")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("artifact flag evidence references must be unique")
        if (self.posterior.state is PosteriorState.NOT_EVALUABLE) != (
            self.disposition is FlagDisposition.NOT_EVALUABLE
        ):
            raise ValueError("artifact flag disposition contradicts posterior state")
        return self


class ExclusionMask(FrozenModel):
    excluded_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0105_MAX_FLAGS)
    review_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0105_MAX_FLAGS)

    @model_validator(mode="after")
    def targets_are_unique_and_disjoint(self) -> ExclusionMask:
        excluded = set(self.excluded_target_ids)
        review = set(self.review_target_ids)
        if len(excluded) != len(self.excluded_target_ids) or len(review) != len(
            self.review_target_ids
        ):
            raise ValueError("exclusion mask target identifiers must be unique")
        if excluded & review:
            raise ValueError("excluded and review targets must be disjoint")
        return self


class ArtifactDetectionResult(FrozenModel):
    output_type: Literal["artifact_detection_result"] = "artifact_detection_result"
    detection_id: Identifier
    result_version: Literal["1.0.0"] = M0105_CONTRACT_VERSION
    request_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: DetectionDisposition
    flags: tuple[ArtifactFlag, ...] = Field(min_length=1, max_length=M0105_MAX_FLAGS)
    exclusion_mask: ExclusionMask
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=512)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def envelope_is_coherent_and_digest_bound(self) -> ArtifactDetectionResult:
        keys = [(flag.target_id, flag.artifact_class) for flag in self.flags]
        if len(keys) != len(set(keys)):
            raise ValueError("artifact flags must be unique by target and class")
        expected_excluded = {
            flag.target_id for flag in self.flags if flag.disposition is FlagDisposition.EXCLUDE
        }
        expected_review = {
            flag.target_id
            for flag in self.flags
            if flag.disposition in {FlagDisposition.REVIEW, FlagDisposition.NOT_EVALUABLE}
        } - expected_excluded
        if set(self.exclusion_mask.excluded_target_ids) != expected_excluded or set(
            self.exclusion_mask.review_target_ids
        ) != expected_review:
            raise ValueError("exclusion mask contradicts artifact flags")
        expected_disposition = (
            DetectionDisposition.QUARANTINED
            if expected_excluded or expected_review
            else DetectionDisposition.ACCEPTED
        )
        if self.disposition is not expected_disposition:
            raise ValueError("artifact detection disposition contradicts its flags")
        _validate_result_envelope(self)
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("artifact detection result digest does not match its content")
        return self


def _validate_result_envelope(result: ArtifactDetectionResult) -> None:
    expected_support = {
        DetectionDisposition.ACCEPTED: (SupportStatus.LIMITED, "artifact_screen_clear"),
        DetectionDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "artifact_screen_quarantined",
        ),
    }[result.disposition]
    if (result.support.status, result.support.reason_code) != expected_support:
        raise ValueError("artifact detection support contradicts its disposition")
    if result.human_review_required is (result.disposition is DetectionDisposition.ACCEPTED):
        raise ValueError("artifact detection review flag contradicts its disposition")
    suffix = result.request_digest.removeprefix("sha256:")
    if result.detection_id != f"detection.m0105.{suffix}":
        raise ValueError("artifact detection identifier does not bind its request digest")
    if result.provenance.activity_id != f"activity.m0105.{suffix}":
        raise ValueError("artifact provenance activity does not bind its request digest")
    if result.provenance.module_id != M0105_MODULE_ID:
        raise ValueError("artifact provenance belongs to the wrong module")
    if result.provenance.module_version != result.result_version:
        raise ValueError("artifact provenance version contradicts the result")
    if result.provenance.generated_at != result.completed_at:
        raise ValueError("artifact provenance timestamp contradicts the result")
    if result.provenance.configuration_digest != result.configuration_digest:
        raise ValueError("artifact provenance contradicts the configuration")
    required = {
        result.request_digest,
        result.configuration_digest,
        *(digest for flag in result.flags for digest in flag.provenance.rule_digests),
        *(digest for flag in result.flags for digest in flag.provenance.signal_digests),
    }
    if not required.issubset(result.provenance.input_digests):
        raise ValueError("artifact provenance input digests are incomplete")
    if any(
        flag.provenance.configuration_digest != result.configuration_digest
        for flag in result.flags
    ):
        raise ValueError("artifact flag provenance contradicts the configuration")
    if len(result.evidence) != len(set(result.evidence)):
        raise ValueError("artifact detection evidence references must be unique")
    if {limitation.code for limitation in result.limitations} != {
        M0105_ARTIFACT_LIMITATION_CODE,
        M0105_AUTHORITY_LIMITATION_CODE,
    }:
        raise ValueError("artifact detection requires both module limitations")


def _require_unique(records: tuple[object, ...], field: str, label: str) -> None:
    values = [getattr(record, field) for record in records]
    if len(values) != len(set(values)):
        raise ValueError(f"{label} identifiers must be unique")


def _require_representable_request(request: DetectArtifactsRequest) -> None:
    target_count = len({signal.target_id for signal in request.signals})
    class_count = len({rule.artifact_class for rule in request.rules})
    if target_count * class_count > M0105_MAX_FLAGS:
        raise ValueError("artifact request would exceed the result flag limit")
    # Provenance records contain request and configuration digests, every rule and signal
    # digest, and six non-configuration control digests. The approved-configuration control
    # reuses the configuration digest, so eight is the conservative fixed overhead.
    if len(request.rules) + len(request.signals) + 8 > M0105_MAX_PROVENANCE_INPUTS:
        raise ValueError("artifact request would exceed the provenance input limit")


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize artifact detection")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before artifact detection")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(reference.state is not UpstreamDecisionState.ACCEPTED for reference in generic):
        raise ValueError("every upstream control must accept artifact detection")


__all__ = [
    "M0105_CONTRACT_VERSION",
    "M0105_MODULE_ID",
    "ArtifactClass",
    "ArtifactDetectionPolicy",
    "ArtifactDetectionResult",
    "ArtifactFlag",
    "ArtifactRule",
    "Comparison",
    "DetectArtifactsRequest",
    "DetectionDisposition",
    "DetectorProfile",
    "ExclusionMask",
    "FlagDisposition",
    "FlagProvenance",
    "PosteriorEstimate",
    "PosteriorState",
    "SignalObservation",
    "SignalState",
]
