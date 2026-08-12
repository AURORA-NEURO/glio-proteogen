"""Strict public contracts for M02-04 identification quality computation."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m02_04.canonical import (
    configuration_digest,
    observation_digest,
    policy_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

M0204_MODULE_ID: Final = "GLIO-PROTEOGEN-M02-04"
M0204_CONTRACT_VERSION: Final = "1.0.0"
M0204_MAX_EVIDENCE_PER_METRIC: Final = 32
M0204_QUALITY_LIMITATION_CODE: Final = "identification_quality_metrics_only"
M0204_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class IdentificationAssayType(StrEnum):
    DDA = "dda"
    DIA = "dia"
    ISOBARIC = "isobaric"
    TARGETED = "targeted"


class IdentificationQualityMetricCode(StrEnum):
    IDENTIFICATION_COVERAGE = "identification_coverage"
    TARGET_DECOY_FDR = "target_decoy_fdr"
    PRECURSOR_MASS_ERROR_ACCURACY = "precursor_mass_error_accuracy"
    IDENTIFICATION_COMPLETENESS = "identification_completeness"
    CONTROL_MATERIAL_RECOVERY = "control_material_recovery"
    SAMPLE_CONTEXT_MATCH = "sample_context_match"


class MetricObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    CENSORED = "censored"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    WITHIN_RANGE = "within_range"


class IdentificationMetricStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - domain status, not a credential.
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class IdentificationQualityDisposition(StrEnum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"


class IdentificationAssayProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    assay_type: IdentificationAssayType
    target_decoy_strategy: Identifier
    precursor_mass_error_unit: Literal["ppm"] = "ppm"
    evidence: ArtifactReference


class MetricObservation(FrozenModel):
    metric_code: IdentificationQualityMetricCode
    state: MetricObservationState
    numerator: FiniteFloat | None = Field(default=None, ge=0.0)
    denominator: FiniteFloat | None = Field(default=None, gt=0.0)
    value: FiniteFloat | bool | None = None
    upper_bound: FiniteFloat | None = Field(default=None, ge=0.0)
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0204_MAX_EVIDENCE_PER_METRIC,
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        values: tuple[ArtifactReference, ...],
    ) -> tuple[ArtifactReference, ...]:
        if len(values) != len(set(values)):
            raise ValueError("metric observation evidence must be unique")
        return values

    @model_validator(mode="after")
    def observation_shape_matches_metric_and_state(  # noqa: PLR0912 - closed union shape.
        self,
    ) -> MetricObservation:
        ratio_codes = {
            IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE,
            IdentificationQualityMetricCode.TARGET_DECOY_FDR,
            IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS,
            IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY,
        }
        if self.state is MetricObservationState.OBSERVED:
            if self.metric_code in ratio_codes:
                if self.numerator is None or self.denominator is None or self.value is not None:
                    raise ValueError("observed ratio metric requires numerator and denominator")
                if (
                    self.metric_code
                    is not IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY
                    and self.numerator > self.denominator
                ):
                    raise ValueError("proportion numerator cannot exceed denominator")
            elif self.metric_code is IdentificationQualityMetricCode.SAMPLE_CONTEXT_MATCH:
                if not isinstance(self.value, bool):
                    raise ValueError("sample-context observation requires a boolean value")
                if self.numerator is not None or self.denominator is not None:
                    raise ValueError("sample-context observation cannot carry ratio inputs")
            else:
                if not isinstance(self.value, float):
                    raise ValueError("mass-error observation requires a numeric value")
                if self.value < 0.0:
                    raise ValueError("mass-error observation cannot be negative")
                if self.numerator is not None or self.denominator is not None:
                    raise ValueError("mass-error observation cannot carry ratio inputs")
            if self.upper_bound is not None:
                raise ValueError("observed metric cannot carry a censoring bound")
        elif self.state is MetricObservationState.CENSORED:
            if self.upper_bound is None:
                raise ValueError("censored metric requires an upper bound")
            if self.value is not None or self.numerator is not None or self.denominator is not None:
                raise ValueError("censored metric cannot carry observed inputs")
        elif any(
            item is not None
            for item in (self.value, self.numerator, self.denominator, self.upper_bound)
        ):
            raise ValueError("nonobserved metric cannot carry values")
        return self


class MetricThreshold(FrozenModel):
    metric_code: IdentificationQualityMetricCode
    direction: MetricDirection
    required: bool = True
    pass_minimum: FiniteFloat | None = None
    pass_maximum: FiniteFloat | None = None
    warning_minimum: FiniteFloat | None = None
    warning_maximum: FiniteFloat | None = None

    @model_validator(mode="after")
    def thresholds_match_direction(self) -> MetricThreshold:
        expected_directions = {
            IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE: (
                MetricDirection.HIGHER_IS_BETTER
            ),
            IdentificationQualityMetricCode.TARGET_DECOY_FDR: (
                MetricDirection.LOWER_IS_BETTER
            ),
            IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY: (
                MetricDirection.LOWER_IS_BETTER
            ),
            IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS: (
                MetricDirection.HIGHER_IS_BETTER
            ),
            IdentificationQualityMetricCode.CONTROL_MATERIAL_RECOVERY: (
                MetricDirection.WITHIN_RANGE
            ),
            IdentificationQualityMetricCode.SAMPLE_CONTEXT_MATCH: (
                MetricDirection.HIGHER_IS_BETTER
            ),
        }
        if self.direction is not expected_directions[self.metric_code]:
            raise ValueError("metric direction contradicts its fixed computation semantics")
        if self.direction is MetricDirection.HIGHER_IS_BETTER and self.pass_minimum is None:
            raise ValueError("higher-is-better metric requires a pass minimum")
        if self.direction is MetricDirection.LOWER_IS_BETTER and self.pass_maximum is None:
            raise ValueError("lower-is-better metric requires a pass maximum")
        if self.direction is MetricDirection.WITHIN_RANGE and (
            self.pass_minimum is None or self.pass_maximum is None
        ):
            raise ValueError("range metric requires pass minimum and maximum")
        if self.direction is MetricDirection.HIGHER_IS_BETTER and (
            self.pass_maximum is not None or self.warning_maximum is not None
        ):
            raise ValueError("higher-is-better metric cannot carry maximum thresholds")
        if self.direction is MetricDirection.LOWER_IS_BETTER and (
            self.pass_minimum is not None or self.warning_minimum is not None
        ):
            raise ValueError("lower-is-better metric cannot carry minimum thresholds")
        if self.direction is MetricDirection.WITHIN_RANGE and (
            (self.warning_minimum is None) is not (self.warning_maximum is None)
        ):
            raise ValueError("range warning thresholds must be supplied together")
        proportion_codes = {
            IdentificationQualityMetricCode.IDENTIFICATION_COVERAGE,
            IdentificationQualityMetricCode.TARGET_DECOY_FDR,
            IdentificationQualityMetricCode.IDENTIFICATION_COMPLETENESS,
            IdentificationQualityMetricCode.SAMPLE_CONTEXT_MATCH,
        }
        if self.metric_code in proportion_codes and any(
            bound is not None and not 0.0 <= bound <= 1.0
            for bound in (
                self.pass_minimum,
                self.pass_maximum,
                self.warning_minimum,
                self.warning_maximum,
            )
        ):
            raise ValueError("proportion metric thresholds must be within zero and one")
        _validate_range(self.pass_minimum, self.pass_maximum, "pass")
        _validate_range(self.warning_minimum, self.warning_maximum, "warning")
        if (
            self.warning_minimum is not None
            and self.pass_minimum is not None
            and self.warning_minimum > self.pass_minimum
        ):
            raise ValueError("warning range must contain pass range")
        if (
            self.warning_maximum is not None
            and self.pass_maximum is not None
            and self.warning_maximum < self.pass_maximum
        ):
            raise ValueError("warning range must contain pass range")
        return self


class IdentificationQualityPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    thresholds: tuple[MetricThreshold, ...] = Field(
        min_length=len(IdentificationQualityMetricCode),
        max_length=len(IdentificationQualityMetricCode),
    )
    quarantine_on_warning: bool = False

    @model_validator(mode="after")
    def policy_governs_every_metric_once(self) -> IdentificationQualityPolicy:
        codes = [item.metric_code for item in self.thresholds]
        if len(codes) != len(set(codes)) or set(codes) != set(IdentificationQualityMetricCode):
            raise ValueError("policy must govern every identification quality metric exactly once")
        return self


class ComputeIdentificationQualityRequest(FrozenModel):
    operation: Literal["compute_identification_quality"] = "compute_identification_quality"
    contract_version: Literal["1.0.0"] = M0204_CONTRACT_VERSION
    context: ExecutionContext
    assay_profile: IdentificationAssayProfile
    policy: IdentificationQualityPolicy
    observations: tuple[MetricObservation, ...] = Field(
        min_length=len(IdentificationQualityMetricCode),
        max_length=len(IdentificationQualityMetricCode),
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_closed_and_bound(self) -> ComputeIdentificationQualityRequest:
        _require_authorized_context(self.context)
        codes = [item.metric_code for item in self.observations]
        if len(codes) != len(set(codes)) or set(codes) != set(IdentificationQualityMetricCode):
            raise ValueError("request requires one observation for every quality metric")
        if self.context.references.approved_configuration.evidence.digest != configuration_digest(
            self.policy
        ):
            raise ValueError("approved configuration does not bind the quality policy")
        return self


class IdentificationMetricProvenance(FrozenModel):
    observation_digest: Sha256Digest
    threshold_digest: Sha256Digest
    assay_profile_digest: Sha256Digest
    policy_digest: Sha256Digest


class IdentificationMetricResult(FrozenModel):
    metric_code: IdentificationQualityMetricCode
    state: MetricObservationState
    status: IdentificationMetricStatus
    required: bool
    value: FiniteFloat | None = None
    unit: Literal["1", "ppm"]
    observation: MetricObservation
    threshold: MetricThreshold
    provenance: IdentificationMetricProvenance
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0204_MAX_EVIDENCE_PER_METRIC,
    )

    @field_validator("evidence")
    @classmethod
    def evidence_is_unique(
        cls,
        values: tuple[ArtifactReference, ...],
    ) -> tuple[ArtifactReference, ...]:
        if len(values) != len(set(values)):
            raise ValueError("metric result evidence must be unique")
        return values

    @model_validator(mode="after")
    def value_matches_status(self) -> IdentificationMetricResult:
        if self.status is IdentificationMetricStatus.NOT_EVALUABLE:
            if self.value is not None or self.state is MetricObservationState.OBSERVED:
                raise ValueError("not-evaluable metric cannot carry an observed value")
        elif self.value is None or self.state is not MetricObservationState.OBSERVED:
            raise ValueError("evaluable metric requires an observed value")
        expected_unit = (
            "ppm"
            if self.metric_code
            is IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY
            else "1"
        )
        if self.unit != expected_unit:
            raise ValueError("metric unit contradicts its metric code")
        if (
            self.threshold.metric_code is not self.metric_code
            or self.threshold.required is not self.required
        ):
            raise ValueError("metric result contradicts its threshold")
        if (
            self.observation.metric_code is not self.metric_code
            or self.observation.state is not self.state
            or set(self.observation.evidence) != set(self.evidence)
        ):
            raise ValueError("metric result contradicts its observation")
        if self.provenance.observation_digest != observation_digest(self.observation):
            raise ValueError("metric observation digest does not match its content")
        if self.provenance.threshold_digest != sha256_digest(self.threshold):
            raise ValueError("metric threshold digest does not match its content")
        if self.value != _metric_value(self.observation):
            raise ValueError("metric value contradicts its observation")
        if self.status is not _classify_metric_result(
            self.state,
            self.value,
            self.threshold,
        ):
            raise ValueError("metric status contradicts its value and threshold")
        return self


class IdentificationQualityProfile(FrozenModel):
    output_type: Literal["identification_quality_profile"] = "identification_quality_profile"
    quality_profile_id: Identifier
    result_version: Literal["1.0.0"] = M0204_CONTRACT_VERSION
    request_digest: Sha256Digest
    assay_profile_digest: Sha256Digest
    assay_profile_evidence_digest: Sha256Digest
    policy_id: Identifier
    policy_version: SemanticVersion
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: IdentificationQualityDisposition
    metrics: tuple[IdentificationMetricResult, ...] = Field(
        min_length=len(IdentificationQualityMetricCode),
        max_length=len(IdentificationQualityMetricCode),
    )
    parent_target: Literal["protein_subtype"] = "protein_subtype"
    quarantine_on_warning: bool
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=8, max_length=8)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def envelope_is_relationally_closed(  # noqa: PLR0912, PLR0915 - explicit safety closure.
        self,
    ) -> IdentificationQualityProfile:
        codes = [item.metric_code for item in self.metrics]
        if len(codes) != len(set(codes)) or set(codes) != set(IdentificationQualityMetricCode):
            raise ValueError("profile requires every quality metric exactly once")
        must_quarantine = any(
            item.status is IdentificationMetricStatus.FAIL
            or (
                item.required
                and item.status is IdentificationMetricStatus.NOT_EVALUABLE
            )
            or (
                self.quarantine_on_warning
                and item.status is IdentificationMetricStatus.WARNING
            )
            for item in self.metrics
        )
        expected_disposition = (
            IdentificationQualityDisposition.QUARANTINED
            if must_quarantine
            else IdentificationQualityDisposition.ACCEPTED
        )
        if self.disposition is not expected_disposition:
            raise ValueError("quality disposition contradicts metric results")
        expected_support = {
            IdentificationQualityDisposition.ACCEPTED: (
                SupportStatus.LIMITED,
                "identification_quality_accepted",
                False,
            ),
            IdentificationQualityDisposition.QUARANTINED: (
                SupportStatus.REVIEW_REQUIRED,
                "identification_quality_quarantined",
                True,
            ),
        }[self.disposition]
        if (
            self.support.status,
            self.support.reason_code,
            self.human_review_required,
        ) != expected_support:
            raise ValueError("quality support contradicts disposition")
        suffix = self.request_digest.removeprefix("sha256:")
        if self.quality_profile_id != f"quality.m0204.{suffix}":
            raise ValueError("quality profile identifier does not bind request")
        provenance = self.provenance
        if (
            provenance.activity_id != f"activity.m0204.{suffix}"
            or provenance.module_id != M0204_MODULE_ID
            or provenance.module_version != self.result_version
            or provenance.generated_at != self.completed_at
            or provenance.configuration_digest != self.configuration_digest
        ):
            raise ValueError("quality provenance is inconsistent")
        required = {
            self.request_digest,
            self.assay_profile_digest,
            self.assay_profile_evidence_digest,
            self.policy_digest,
            self.configuration_digest,
            *(item.provenance.observation_digest for item in self.metrics),
            *(item.provenance.threshold_digest for item in self.metrics),
            *(item.evidence_digest for item in provenance.control_decisions),
        }
        if not required.issubset(provenance.input_digests):
            raise ValueError("quality provenance inputs are incomplete")
        if any(
            item.provenance.assay_profile_digest != self.assay_profile_digest
            or item.provenance.policy_digest != self.policy_digest
            for item in self.metrics
        ):
            raise ValueError("metric provenance contradicts profile digests")
        reconstructed_policy = IdentificationQualityPolicy(
            policy_id=self.policy_id,
            version=self.policy_version,
            thresholds=tuple(item.threshold for item in self.metrics),
            quarantine_on_warning=self.quarantine_on_warning,
        )
        if policy_digest(reconstructed_policy) != self.policy_digest:
            raise ValueError("quality profile thresholds do not bind its policy digest")
        if {item.code for item in self.limitations} != {
            M0204_QUALITY_LIMITATION_CODE,
            M0204_AUTHORITY_LIMITATION_CODE,
        }:
            raise ValueError("quality profile requires both limitation codes")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("quality profile evidence must be unique")
        evidence_digests = {item.reference.digest for item in self.evidence}
        expected_evidence_digests = {
            self.assay_profile_evidence_digest,
            *(item.evidence_digest for item in provenance.control_decisions),
        }
        if evidence_digests != expected_evidence_digests:
            raise ValueError("quality evidence must contain exactly controls and assay profile")
        configuration = next(
            item
            for item in provenance.control_decisions
            if item.role.value == "approved_configuration"
        )
        if configuration.evidence_digest != self.configuration_digest:
            raise ValueError("approved configuration evidence does not bind result")
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
        if {role: item.state for role, item in controls.items()} != expected_states:
            raise ValueError("quality control states are inconsistent")
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
            raise ValueError("quality consent provenance contradicts its control record")
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
                self.assay_profile_evidence_digest,
                "evidence",
                "Caller-declared assay profile evidence; issuer is not authenticated.",
            )
        )
        actual_evidence_claims = {
            (item.reference.digest, item.role, item.claim) for item in self.evidence
        }
        if actual_evidence_claims != expected_evidence_claims:
            raise ValueError("quality evidence claims are inconsistent")
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("quality profile digest does not match content")
        return self


def _validate_range(lower: float | None, upper: float | None, label: str) -> None:
    if lower is not None and upper is not None and lower > upper:
        raise ValueError(f"{label} minimum cannot exceed maximum")


def _classify_metric_result(  # noqa: PLR0911 - direct closed threshold classification.
    state: MetricObservationState,
    value: float | None,
    threshold: MetricThreshold,
) -> IdentificationMetricStatus:
    if state is not MetricObservationState.OBSERVED or value is None:
        return IdentificationMetricStatus.NOT_EVALUABLE
    if threshold.direction is MetricDirection.HIGHER_IS_BETTER:
        if threshold.pass_minimum is not None and value >= threshold.pass_minimum:
            return IdentificationMetricStatus.PASS
        if threshold.warning_minimum is not None and value >= threshold.warning_minimum:
            return IdentificationMetricStatus.WARNING
        return IdentificationMetricStatus.FAIL
    if threshold.direction is MetricDirection.LOWER_IS_BETTER:
        if threshold.pass_maximum is not None and value <= threshold.pass_maximum:
            return IdentificationMetricStatus.PASS
        if threshold.warning_maximum is not None and value <= threshold.warning_maximum:
            return IdentificationMetricStatus.WARNING
        return IdentificationMetricStatus.FAIL
    if (
        threshold.pass_minimum is not None
        and threshold.pass_maximum is not None
        and threshold.pass_minimum <= value <= threshold.pass_maximum
    ):
        return IdentificationMetricStatus.PASS
    if (
        threshold.warning_minimum is not None
        and threshold.warning_maximum is not None
        and threshold.warning_minimum <= value <= threshold.warning_maximum
    ):
        return IdentificationMetricStatus.WARNING
    return IdentificationMetricStatus.FAIL


def _metric_value(observation: MetricObservation) -> float | None:
    if observation.state is not MetricObservationState.OBSERVED:
        return None
    if observation.metric_code is IdentificationQualityMetricCode.SAMPLE_CONTEXT_MATCH:
        return 1.0 if observation.value is True else 0.0
    if observation.metric_code is IdentificationQualityMetricCode.PRECURSOR_MASS_ERROR_ACCURACY:
        return observation.value if isinstance(observation.value, float) else None
    if observation.numerator is None or observation.denominator is None:
        return None
    return observation.numerator / observation.denominator


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize identification quality computation")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before quality computation")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic):
        raise ValueError("every upstream control must accept quality computation")


__all__ = [
    "M0204_AUTHORITY_LIMITATION_CODE",
    "M0204_CONTRACT_VERSION",
    "M0204_MAX_EVIDENCE_PER_METRIC",
    "M0204_MODULE_ID",
    "M0204_QUALITY_LIMITATION_CODE",
    "ComputeIdentificationQualityRequest",
    "FiniteFloat",
    "IdentificationAssayProfile",
    "IdentificationAssayType",
    "IdentificationMetricProvenance",
    "IdentificationMetricResult",
    "IdentificationMetricStatus",
    "IdentificationQualityDisposition",
    "IdentificationQualityMetricCode",
    "IdentificationQualityPolicy",
    "IdentificationQualityProfile",
    "MetricDirection",
    "MetricObservation",
    "MetricObservationState",
    "MetricThreshold",
]
