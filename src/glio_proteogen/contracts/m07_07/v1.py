"""Provisional M07-07 calibration and selective-prediction contracts.

The dossier freezes the safety intent and calibration dimensions, but not the
public ABI, strata catalogue, calibration metrics, or coverage ceilings.  The
types in this module are therefore explicitly provisional and fail closed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m07_06.canonical import canonical_request_digest
from glio_proteogen.contracts.m07_06.v1 import (  # noqa: TC001
    CopyNumberDosageUncertaintyDecompositionResult,
)
from glio_proteogen.contracts.m07_07.canonical import result_payload_digest
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
    SupportStatus,
    UncertaintyProfile,
)

M0707_MODULE_ID: Final = "GLIO-PROTEOGEN-M07-07"
M0707_OPERATION: Final = "calibrate_selective_copy_number_dosage"
M0707_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0707_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-07+json"
M0707_PARENT: Final = "proteotype"
M0707_OWNER: Final = "Quality engineering"
M0707_SAFETY_CLASS: Final = "S2"
M0707_GATE: Final = "G3"
M0707_PROVISIONAL_ABI: Final = True
M0707_MAX_STRATA: Final = 64
M0707_MAX_ESTIMATES: Final = 512
M0707_MAX_CANDIDATES: Final = 512
M0707_MAX_PREDICTION_SET_LABELS: Final = 128
M0707_MAX_DIAGNOSTICS: Final = 256
M0707_MAX_EVIDENCE: Final = 32
M0707_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0707_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0707_NOMINAL_COVERAGE: Final = 0.90
M0707_MIN_COVERAGE: Final = 0.85
M0707_MAX_COVERAGE: Final = 0.95
M0707_MAX_CALIBRATION_ERROR: Final = 0.10
M0707_EVIDENCE_CLAIM: Final = (
    "Caller-declared calibration and selective-prediction evidence; "
    "issuer authority is not authenticated."
)


class CalibrationStratumDimension(StrEnum):
    SITE = "site"
    PLATFORM = "platform"
    DISEASE_CLASS = "disease_class"
    SUBGROUP = "subgroup"


class CalibrationMethod(StrEnum):
    CONFORMAL = "conformal"
    TEMPERATURE_SCALING = "temperature_scaling"
    ISOTONIC = "isotonic"
    EMPIRICAL_QUANTILE = "empirical_quantile"


class OutOfDistributionStatus(StrEnum):
    IN_DOMAIN = "in_domain"
    OOD = "ood"
    NOT_EVALUABLE = "not_evaluable"


class CalibrationStatus(StrEnum):
    CALIBRATED = "calibrated"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class SelectivePredictionStatus(StrEnum):
    SELECTED = "selected"
    ABSTAINED = "abstained"


class CalibrationStratum(FrozenModel):
    stratum_id: Identifier
    dimension: CalibrationStratumDimension
    label: NonEmptyStr
    sample_count: int = Field(ge=0)
    observed_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    calibration_error: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def coverage_requires_samples(self) -> CalibrationStratum:
        if self.sample_count == 0 and (
            self.observed_coverage is not None or self.calibration_error is not None
        ):
            raise ValueError("coverage metrics require a non-empty calibration stratum")
        return self


class SelectiveSupportThreshold(FrozenModel):
    threshold_id: Identifier
    version: SemanticVersion
    minimum_support_score: float = Field(ge=0.0, le=1.0)
    maximum_ood_score: float = Field(ge=0.0, le=1.0)
    maximum_calibration_error: float = Field(ge=0.0, le=1.0)
    target_coverage: float = Field(ge=0.0, le=1.0)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0707_MAX_EVIDENCE)


class CalibrationPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    method: CalibrationMethod
    target_coverage: float = Field(default=M0707_NOMINAL_COVERAGE, ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    strata: tuple[CalibrationStratum, ...] = Field(
        min_length=1, max_length=M0707_MAX_STRATA
    )
    support_threshold: SelectiveSupportThreshold
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def policy_is_closed(self) -> CalibrationPolicy:
        if len({item.stratum_id for item in self.strata}) != len(self.strata):
            raise ValueError("calibration stratum ids must be unique")
        if self.support_threshold.target_coverage != self.target_coverage:
            raise ValueError("support threshold must bind policy target coverage")
        return self


class CalibratedPredictionSet(FrozenModel):
    prediction_set_id: Identifier
    feature_id: Identifier
    labels: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M0707_MAX_PREDICTION_SET_LABELS
    )
    target_coverage: float = Field(ge=0.0, le=1.0)
    observed_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    abstention_allowed: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def labels_are_unique(self) -> CalibratedPredictionSet:
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("prediction-set labels must be unique")
        return self


class CalibratedEstimate(FrozenModel):
    feature_id: Identifier
    estimate_value: float | None = None
    category: NonEmptyStr | None = None
    prediction_set_id: Identifier | None = None
    support_score: float = Field(ge=0.0, le=1.0)
    ood_status: OutOfDistributionStatus
    calibration_error: float | None = Field(default=None, ge=0.0, le=1.0)
    selection_status: SelectivePredictionStatus
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def selected_estimate_is_closed(self) -> CalibratedEstimate:
        if self.selection_status is SelectivePredictionStatus.SELECTED:
            if self.ood_status is not OutOfDistributionStatus.IN_DOMAIN:
                raise ValueError("selected estimate must be in-domain")
            if self.estimate_value is None and self.category is None:
                raise ValueError("selected estimate requires a value or category")
            if self.calibration_error is None:
                raise ValueError("selected estimate requires calibration error")
        elif self.estimate_value is not None or self.category is not None:
            raise ValueError("abstained estimate cannot carry a scientific value")
        return self


class CalibrationDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: CalibrationStatus
    metric_name: NonEmptyStr
    metric_value: float | None = Field(default=None, ge=0.0, le=1.0)
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0707_MAX_EVIDENCE)


class SelectiveCandidate(FrozenModel):
    """Caller-declared candidate used by the provisional selective gate.

    This is deliberately an opaque, content-addressed declaration rather than a
    model output.  M07-07 may select it only after the upstream M07-06 result,
    calibration strata, and support/OOD thresholds have all passed.  The
    candidate is never inferred from an artifact reference or from missing data.
    """

    feature_id: Identifier
    estimate_value: float | None = None
    category: NonEmptyStr | None = None
    labels: tuple[NonEmptyStr, ...] = Field(default=(), max_length=M0707_MAX_PREDICTION_SET_LABELS)
    support_score: float = Field(ge=0.0, le=1.0)
    ood_score: float = Field(ge=0.0, le=1.0)
    calibration_error: float = Field(ge=0.0, le=1.0)
    stratum_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=4)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def candidate_value_is_closed(self) -> SelectiveCandidate:
        if (self.estimate_value is None) == (self.category is None):
            raise ValueError("candidate requires exactly one estimate value or category")
        if self.labels and len(set(self.labels)) != len(self.labels):
            raise ValueError("candidate prediction labels must be unique")
        if not self.labels and self.category is None:
            raise ValueError("numeric candidate requires a non-empty prediction label set")
        if len(set(self.stratum_ids)) != len(self.stratum_ids):
            raise ValueError("candidate stratum ids must be unique")
        return self


class CalibrateSelectiveCopyNumberDosageRequest(FrozenModel):
    """Provisional request bound to the complete M07-06 uncertainty result."""

    operation: Literal["calibrate_selective_copy_number_dosage"] = M0707_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0707_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    uncertainty_result: CopyNumberDosageUncertaintyDecompositionResult
    policy: CalibrationPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0707_MAX_EVIDENCE
    )
    candidates: tuple[SelectiveCandidate, ...] = Field(
        default=(), max_length=M0707_MAX_CANDIDATES
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> CalibrateSelectiveCopyNumberDosageRequest:
        if self.uncertainty_result.output_type != "copy_number_dosage_uncertainty_decomposition":
            raise ValueError("calibration request must bind the complete M07-06 result")
        if self.uncertainty_result.result_version != "0.1.0-provisional":
            raise ValueError("calibration request must bind the provisional M07-06 version")
        if self.policy.target_coverage != M0707_NOMINAL_COVERAGE:
            raise ValueError("provisional calibration gate requires nominal 90 percent coverage")
        return self


class CalibrateSelectiveCopyNumberDosageResult(FrozenModel):
    """Calibrated estimate/prediction set with explicit selective abstention."""

    output_type: Literal["copy_number_dosage_calibrated_prediction"] = (
        "copy_number_dosage_calibrated_prediction"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0707_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: CalibrateSelectiveCopyNumberDosageRequest
    status: CalibrationStatus
    estimates: tuple[CalibratedEstimate, ...] = Field(default=(), max_length=M0707_MAX_ESTIMATES)
    prediction_sets: tuple[CalibratedPredictionSet, ...] = Field(
        default=(), max_length=M0707_MAX_ESTIMATES
    )
    diagnostics: tuple[CalibrationDiagnostic, ...] = Field(
        default=(), max_length=M0707_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M0707_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0707_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> CalibrateSelectiveCopyNumberDosageResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is CalibrationStatus.CALIBRATED:
            if not self.estimates or self.abstention_reason is not None:
                raise ValueError("calibrated result requires selected or abstained estimates")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("calibrated result requires supported status")
        elif (
            self.estimates
            or self.prediction_sets
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no predictions and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0707_CONTRACT_VERSION",
    "M0707_EVIDENCE_CLAIM",
    "M0707_GATE",
    "M0707_MAX_CALIBRATION_ERROR",
    "M0707_MAX_CANONICAL_REQUEST_BYTES",
    "M0707_MAX_CANONICAL_RESULT_BYTES",
    "M0707_MAX_CANDIDATES",
    "M0707_MAX_COVERAGE",
    "M0707_MAX_DIAGNOSTICS",
    "M0707_MAX_ESTIMATES",
    "M0707_MAX_EVIDENCE",
    "M0707_MAX_PREDICTION_SET_LABELS",
    "M0707_MAX_STRATA",
    "M0707_MIN_COVERAGE",
    "M0707_MODULE_ID",
    "M0707_NOMINAL_COVERAGE",
    "M0707_OPERATION",
    "M0707_OUTPUT_MEDIA_TYPE",
    "M0707_OWNER",
    "M0707_PARENT",
    "M0707_PROVISIONAL_ABI",
    "M0707_SAFETY_CLASS",
    "CalibrateSelectiveCopyNumberDosageRequest",
    "CalibrateSelectiveCopyNumberDosageResult",
    "CalibratedEstimate",
    "CalibratedPredictionSet",
    "CalibrationDiagnostic",
    "CalibrationMethod",
    "CalibrationPolicy",
    "CalibrationStatus",
    "CalibrationStratum",
    "CalibrationStratumDimension",
    "OutOfDistributionStatus",
    "SelectivePredictionStatus",
    "SelectiveCandidate",
    "SelectiveSupportThreshold",
]
