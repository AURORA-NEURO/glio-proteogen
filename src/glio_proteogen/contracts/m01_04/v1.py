"""Strict public contracts for M01-04 quality metric computation."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from glio_proteogen.contracts.m01_04.canonical import policy_digest, result_payload_digest
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

M0104_MODULE_ID: Final = "GLIO-PROTEOGEN-M01-04"
M0104_CONTRACT_VERSION: Final = "1.0.0"
M0104_MAX_METRICS: Final = 256
M0104_MAX_OBSERVATIONS: Final = 4_096
M0104_MAX_EVIDENCE_PER_ITEM: Final = 64
M0104_QUALITY_LIMITATION_CODE: Final = "quality_metrics_only"
M0104_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)

MetricUnit = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9%][A-Za-z0-9%._/*^-]*$"),
]


class AssayType(StrEnum):
    DDA = "dda"
    DIA = "dia"
    ISOBARIC = "isobaric"
    TARGETED = "targeted"


class AnalyteLevel(StrEnum):
    PEPTIDE = "peptide"
    PROTEIN = "protein"
    PROTEOFORM = "proteoform"
    PTM_SITE = "ptm_site"


class Computation(StrEnum):
    DIRECT = "direct"
    RATIO = "ratio"
    DETECTION_MARGIN = "detection_margin"
    RELATIVE_ERROR = "relative_error"
    BOOLEAN_MATCH = "boolean_match"


class MetricCategory(StrEnum):
    COVERAGE = "coverage"
    DETECTION_LIMIT = "detection_limit"
    COMPLETENESS = "completeness"
    CONTROL_MATERIAL = "control_material"
    SAMPLE_CONTEXT = "sample_context"
    ASSAY_QUALITY = "assay_quality"


class MetricState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    BELOW_DETECTION = "below_detection"
    NOT_APPLICABLE = "not_applicable"


class MetricStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - domain status, not a credential
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class QualityDisposition(StrEnum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"


class AssayProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    assay_type: AssayType
    analyte_level: AnalyteLevel
    required_metric_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0104_MAX_METRICS,
    )
    evidence: ArtifactReference

    @field_validator("required_metric_ids")
    @classmethod
    def required_metrics_are_unique(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("assay profile metric identifiers must be unique")
        return values


class MetricDefinition(FrozenModel):
    metric_id: Identifier
    version: SemanticVersion
    category: MetricCategory
    computation: Computation
    unit: MetricUnit | None = None
    observation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    reference_value: float | bool | None = None
    pass_minimum: float | None = None
    pass_maximum: float | None = None
    warning_minimum: float | None = None
    warning_maximum: float | None = None

    @model_validator(mode="after")
    def computation_and_thresholds_are_closed(self) -> MetricDefinition:
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("metric definition observation identifiers must be unique")
        expected_count = 2 if self.computation is Computation.RATIO else 1
        if len(self.observation_ids) != expected_count:
            raise ValueError("metric computation has invalid observation cardinality")
        if self.computation in {Computation.DETECTION_MARGIN, Computation.RELATIVE_ERROR} and not (
            isinstance(self.reference_value, float)
        ):
            raise ValueError("metric computation requires a numeric reference value")
        if self.computation is Computation.RELATIVE_ERROR and self.reference_value == 0.0:
            raise ValueError("relative-error reference value cannot be zero")
        if self.computation is Computation.BOOLEAN_MATCH and not isinstance(
            self.reference_value,
            bool,
        ):
            raise ValueError("boolean-match computation requires a boolean reference value")
        if self.computation is not Computation.BOOLEAN_MATCH and (
            self.pass_minimum is None and self.pass_maximum is None
        ):
            raise ValueError("numeric metric definitions require a pass boundary")
        _validate_range(self.pass_minimum, self.pass_maximum, "pass")
        _validate_range(self.warning_minimum, self.warning_maximum, "warning")
        if (
            self.warning_minimum is not None
            and self.pass_minimum is not None
            and self.warning_minimum > self.pass_minimum
        ):
            raise ValueError("warning range must contain the pass range")
        if (
            self.warning_maximum is not None
            and self.pass_maximum is not None
            and self.warning_maximum < self.pass_maximum
        ):
            raise ValueError("warning range must contain the pass range")
        return self


class Observation(FrozenModel):
    observation_id: Identifier
    state: MetricState
    value: float | bool | None = None
    unit: MetricUnit | None = None
    detection_limit: float | None = Field(default=None, ge=0.0)
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0104_MAX_EVIDENCE_PER_ITEM,
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        evidence: tuple[ArtifactReference, ...],
    ) -> tuple[ArtifactReference, ...]:
        if len(evidence) != len(set(evidence)):
            raise ValueError("observation evidence references must be unique")
        return evidence

    @model_validator(mode="after")
    def value_matches_state(self) -> Observation:
        if self.state is MetricState.OBSERVED and self.value is None:
            raise ValueError("observed quality input requires a value")
        if self.state is not MetricState.OBSERVED and self.value is not None:
            raise ValueError("non-observed quality input cannot carry a value")
        if self.state is MetricState.BELOW_DETECTION and self.detection_limit is None:
            raise ValueError("below-detection input requires a detection limit")
        if self.state is not MetricState.BELOW_DETECTION and self.detection_limit is not None:
            raise ValueError("only below-detection input may carry a detection limit")
        return self


class Provenance(FrozenModel):
    definition_digest: Sha256Digest
    observation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    observation_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=16)
    computation: Computation
    policy_digest: Sha256Digest

    @model_validator(mode="after")
    def observations_are_positionally_bound(self) -> Provenance:
        if len(self.observation_ids) != len(self.observation_digests):
            raise ValueError("metric provenance observations and digests must align")
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("metric provenance observation identifiers must be unique")
        return self


class QualityMetric(FrozenModel):
    metric_id: Identifier
    definition_version: SemanticVersion
    category: MetricCategory
    computation: Computation
    state: MetricState
    status: MetricStatus
    value: float | bool | None = None
    unit: MetricUnit | None = None
    provenance: Provenance
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0104_MAX_EVIDENCE_PER_ITEM,
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        evidence: tuple[ArtifactReference, ...],
    ) -> tuple[ArtifactReference, ...]:
        if len(evidence) != len(set(evidence)):
            raise ValueError("quality metric evidence references must be unique")
        return evidence

    @model_validator(mode="after")
    def result_matches_state(self) -> QualityMetric:
        if self.state is MetricState.OBSERVED:
            if self.value is None or self.status is MetricStatus.NOT_EVALUABLE:
                raise ValueError("observed quality metric requires an evaluable value")
        elif self.value is not None or self.status is not MetricStatus.NOT_EVALUABLE:
            raise ValueError("non-observed quality metric must be not evaluable")
        if self.provenance.computation is not self.computation:
            raise ValueError("quality metric contradicts its computation provenance")
        return self


class QualityComputationPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    enabled_categories: tuple[MetricCategory, ...] = Field(
        min_length=1,
        max_length=len(MetricCategory),
    )
    require_complete_profile: bool = True
    quarantine_on_warning: bool = False
    max_metrics: int = Field(default=M0104_MAX_METRICS, gt=0, le=M0104_MAX_METRICS)

    @field_validator("enabled_categories")
    @classmethod
    def categories_are_unique(
        cls,
        values: tuple[MetricCategory, ...],
    ) -> tuple[MetricCategory, ...]:
        if len(values) != len(set(values)):
            raise ValueError("enabled metric categories must be unique")
        return values


class ComputeQualityMetricsRequest(FrozenModel):
    operation: Literal["compute_quality_metrics"] = "compute_quality_metrics"
    contract_version: Literal["1.0.0"] = M0104_CONTRACT_VERSION
    context: ExecutionContext
    assay_profile: AssayProfile
    policy: QualityComputationPolicy
    metric_definitions: tuple[MetricDefinition, ...] = Field(
        min_length=1,
        max_length=M0104_MAX_METRICS,
    )
    observations: tuple[Observation, ...] = Field(
        min_length=1,
        max_length=M0104_MAX_OBSERVATIONS,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_closed_and_policy_bound(self) -> ComputeQualityMetricsRequest:
        _require_authorized_context(self.context)
        _require_unique(self.metric_definitions, "metric_id", "metric definition")
        _require_unique(self.observations, "observation_id", "observation")
        if len(self.metric_definitions) > self.policy.max_metrics:
            raise ValueError("metric definition count exceeds the active policy")
        definitions = {definition.metric_id: definition for definition in self.metric_definitions}
        if not set(self.assay_profile.required_metric_ids).issubset(definitions):
            raise ValueError("assay profile references an undefined required metric")
        observation_ids = {observation.observation_id for observation in self.observations}
        if any(
            not set(definition.observation_ids).issubset(observation_ids)
            for definition in self.metric_definitions
        ):
            raise ValueError("metric definition references an unknown observation")
        if any(
            definition.category not in self.policy.enabled_categories
            for definition in self.metric_definitions
        ):
            raise ValueError("metric definition category is disabled by the active policy")
        if self.context.references.approved_configuration.evidence.digest != policy_digest(
            self.policy
        ):
            raise ValueError("approved configuration does not bind the quality policy")
        return self


class QualityProfile(FrozenModel):
    output_type: Literal["quality_profile"] = "quality_profile"
    quality_profile_id: Identifier
    result_version: Literal["1.0.0"] = M0104_CONTRACT_VERSION
    request_digest: Sha256Digest
    assay_profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: QualityDisposition
    metrics: tuple[QualityMetric, ...] = Field(min_length=1, max_length=M0104_MAX_METRICS)
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=512)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def envelope_is_coherent_and_digest_bound(self) -> QualityProfile:
        _require_unique(self.metrics, "metric_id", "quality metric")
        _validate_profile_decision(self)
        _validate_profile_provenance(self)
        _validate_profile_envelope(self)
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("quality profile digest does not match its content")
        return self


def _validate_profile_decision(profile: QualityProfile) -> None:
    statuses = {metric.status for metric in profile.metrics}
    if (
        MetricStatus.FAIL in statuses
        and profile.disposition is not QualityDisposition.QUARANTINED
    ):
        raise ValueError("a failed quality metric requires quarantine")
    if statuses == {MetricStatus.PASS} and profile.disposition is not QualityDisposition.ACCEPTED:
        raise ValueError("an all-passing quality profile must be accepted")
    expected_support = {
        QualityDisposition.ACCEPTED: (SupportStatus.LIMITED, "quality_profile_accepted"),
        QualityDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "quality_profile_quarantined",
        ),
    }[profile.disposition]
    if (profile.support.status, profile.support.reason_code) != expected_support:
        raise ValueError("quality support contradicts its disposition")
    if profile.human_review_required is (profile.disposition is QualityDisposition.ACCEPTED):
        raise ValueError("quality review flag contradicts its disposition")


def _validate_profile_provenance(profile: QualityProfile) -> None:
    provenance = profile.provenance
    suffix = profile.request_digest.removeprefix("sha256:")
    if profile.quality_profile_id != f"quality.m0104.{suffix}":
        raise ValueError("quality profile identifier does not bind its request digest")
    if provenance.activity_id != f"activity.m0104.{suffix}":
        raise ValueError("quality provenance activity does not bind its request digest")
    if provenance.module_id != M0104_MODULE_ID:
        raise ValueError("quality provenance belongs to the wrong module")
    if provenance.module_version != profile.result_version:
        raise ValueError("quality provenance version contradicts the result")
    if provenance.generated_at != profile.completed_at:
        raise ValueError("quality provenance timestamp contradicts the result")
    if provenance.configuration_digest != profile.policy_digest:
        raise ValueError("quality provenance configuration contradicts the policy")
    required_digests = {
        profile.request_digest,
        profile.assay_profile_digest,
        profile.policy_digest,
        *(metric.provenance.definition_digest for metric in profile.metrics),
        *(
            digest
            for metric in profile.metrics
            for digest in metric.provenance.observation_digests
        ),
    }
    if not required_digests.issubset(provenance.input_digests):
        raise ValueError("quality provenance input digests are incomplete")
    if any(
        metric.provenance.policy_digest != profile.policy_digest
        for metric in profile.metrics
    ):
        raise ValueError("quality metric provenance contradicts the active policy")


def _validate_profile_envelope(profile: QualityProfile) -> None:
    if len(profile.evidence) != len(set(profile.evidence)):
        raise ValueError("quality profile evidence references must be unique")
    limitation_codes = {limitation.code for limitation in profile.limitations}
    if limitation_codes != {
        M0104_QUALITY_LIMITATION_CODE,
        M0104_AUTHORITY_LIMITATION_CODE,
    }:
        raise ValueError("quality profile requires both module limitations")


def _validate_range(lower: float | None, upper: float | None, label: str) -> None:
    if lower is not None and upper is not None and lower > upper:
        raise ValueError(f"{label} minimum cannot exceed its maximum")


def _require_unique(records: tuple[object, ...], field: str, label: str) -> None:
    values = [getattr(record, field) for record in records]
    if len(values) != len(set(values)):
        raise ValueError(f"{label} identifiers must be unique")


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize quality computation")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before quality computation")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(reference.state is not UpstreamDecisionState.ACCEPTED for reference in generic):
        raise ValueError("every upstream control must accept quality computation")


QualityMetricComputation = Computation
QualityMetricCategory = MetricCategory
QualityMetricState = MetricState
QualityMetricStatus = MetricStatus

__all__ = [
    "M0104_CONTRACT_VERSION",
    "M0104_MODULE_ID",
    "AnalyteLevel",
    "AssayProfile",
    "AssayType",
    "Computation",
    "ComputeQualityMetricsRequest",
    "MetricCategory",
    "MetricDefinition",
    "MetricState",
    "MetricStatus",
    "Observation",
    "Provenance",
    "QualityComputationPolicy",
    "QualityDisposition",
    "QualityMetric",
    "QualityMetricCategory",
    "QualityMetricComputation",
    "QualityMetricState",
    "QualityMetricStatus",
    "QualityProfile",
]
