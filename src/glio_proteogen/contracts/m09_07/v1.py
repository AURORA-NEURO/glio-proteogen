"""Provisional M09-07 calibration and selective-prediction contracts.

The dossier specifies scoped calibration, support thresholds, OOD checks, and
abstention, but does not freeze the public ABI, metrics, or calibration
catalogue.  These symbols are reviewable scaffolding only.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m09_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
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

M0907_MODULE_ID: Final = "GLIO-PROTEOGEN-M09-07"
M0907_OPERATION: Final = "calibrate_complex_activity_selective_prediction"
M0907_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0907_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-07+json"
M0907_UNCERTAINTY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-06+json"
M0907_PARENT: Final = "complex_activity"
M0907_OWNER: Final = "Data engineering"
M0907_SAFETY_CLASS: Final = "S2"
M0907_GATE: Final = "G3"
M0907_PROVISIONAL_ABI: Final = True
M0907_MAX_PREDICTION_SET: Final = 256
M0907_MAX_DIAGNOSTICS: Final = 256
M0907_MAX_EVIDENCE: Final = 64
M0907_MAX_SCOPES: Final = 128
M0907_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0907_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0907_NOMINAL_COVERAGE: Final = 0.9
M0907_MIN_COVERAGE: Final = 0.85
M0907_MAX_COVERAGE: Final = 0.95
M0907_EVIDENCE_CLAIM: Final = (
    "Caller-declared M09-06 uncertainty and calibration evidence; issuer authority "
    "is not authenticated."
)


class CalibrationMethod(StrEnum):
    CONFORMAL = "conformal"
    SCORE_CALIBRATION = "score_calibration"
    SELECTIVE_ENSEMBLE = "selective_ensemble"


class CalibrationStatus(StrEnum):
    CALIBRATED = "calibrated"
    ABSTAINED = "abstained"


class CalibrationDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class CalibrationFindingCode(StrEnum):
    CALIBRATION_NOT_LOCKED = "calibration_not_locked"
    OOD_UNSUPPORTED = "ood_unsupported"
    SUPPORT_THRESHOLD_NOT_MET = "support_threshold_not_met"
    SUBGROUP_DISPARITY = "subgroup_disparity"


class CalibrationScope(FrozenModel):
    """Explicit site/platform/disease/subgroup calibration scope."""

    site: NonEmptyStr
    platform: NonEmptyStr
    disease_class: NonEmptyStr
    subgroup: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0907_MAX_EVIDENCE)


class CalibrationConfiguration(FrozenModel):
    """Locked calibration and selective-support policy."""

    configuration_id: Identifier
    version: SemanticVersion
    method: CalibrationMethod
    scopes: tuple[CalibrationScope, ...] = Field(
        min_length=1, max_length=M0907_MAX_SCOPES
    )
    nominal_coverage: float = Field(default=M0907_NOMINAL_COVERAGE, ge=0.0, le=1.0)
    support_threshold: float = Field(ge=0.0, le=1.0)
    ood_threshold: float = Field(ge=0.0, le=1.0)
    calibration_artifact: ArtifactReference
    benchmark_artifact: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0907_MAX_EVIDENCE)

    @model_validator(mode="after")
    def scopes_are_unique(self) -> CalibrationConfiguration:
        keys = tuple(
            (item.site, item.platform, item.disease_class, item.subgroup) for item in self.scopes
        )
        if len(keys) != len(set(keys)):
            raise ValueError("calibration scopes must be unique")
        if self.nominal_coverage != M0907_NOMINAL_COVERAGE:
            raise ValueError("provisional selective coverage target must be nominal 90 percent")
        return self


class CalibratedEstimate(FrozenModel):
    predicted_complex_activity: NonEmptyStr
    score: float = Field(ge=0.0, le=1.0)
    calibrated_confidence: float = Field(ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0907_MAX_EVIDENCE)


class PredictionSet(FrozenModel):
    labels: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M0907_MAX_PREDICTION_SET
    )
    nominal_coverage: float = Field(ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0907_MAX_EVIDENCE)

    @model_validator(mode="after")
    def labels_are_unique(self) -> PredictionSet:
        if len(self.labels) != len(set(self.labels)):
            raise ValueError("prediction-set labels must be unique")
        return self


class CalibrationDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: CalibrationDiagnosticStatus
    metric_name: NonEmptyStr
    metric_value: float | None = Field(default=None, ge=0.0, le=1.0)
    subgroup: NonEmptyStr | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0907_MAX_EVIDENCE)


class CalibrateComplexActivitySelectivePredictionRequest(FrozenModel):
    """Provisional request bound to the complete M09-06 uncertainty result."""

    operation: Literal["calibrate_complex_activity_selective_prediction"] = M0907_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0907_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    uncertainty_result: ArtifactReference
    configuration: CalibrationConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0907_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> CalibrateComplexActivitySelectivePredictionRequest:
        if self.uncertainty_result.media_type != M0907_UNCERTAINTY_MEDIA_TYPE:
            raise ValueError("calibration request must bind the provisional M09-06 result")
        return self


class ComplexActivitySelectivePredictionResult(FrozenModel):
    """Calibrated estimate, prediction set, and support decision with safe status."""

    output_type: Literal["complex_activity_selective_prediction"] = (
        "complex_activity_selective_prediction"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0907_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: CalibrateComplexActivitySelectivePredictionRequest
    status: CalibrationStatus
    estimate: CalibratedEstimate | None = None
    prediction_set: PredictionSet | None = None
    diagnostics: tuple[CalibrationDiagnostic, ...] = Field(
        min_length=1, max_length=M0907_MAX_DIAGNOSTICS
    )
    findings: tuple[CalibrationFindingCode, ...] = Field(default=(), max_length=32)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M0907_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0907_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivitySelectivePredictionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        failed = {
            CalibrationDiagnosticStatus.FAIL,
            CalibrationDiagnosticStatus.NOT_EVALUABLE,
        }
        if self.status is CalibrationStatus.CALIBRATED:
            if (
                self.estimate is None
                or self.prediction_set is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed for item in self.diagnostics)
            ):
                raise ValueError("calibrated result requires supported, evaluable output")
        elif (
            self.estimate is not None
            or self.prediction_set is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no prediction and explicit safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0907_CONTRACT_VERSION",
    "M0907_EVIDENCE_CLAIM",
    "M0907_GATE",
    "M0907_MAX_CANONICAL_REQUEST_BYTES",
    "M0907_MAX_CANONICAL_RESULT_BYTES",
    "M0907_MAX_COVERAGE",
    "M0907_MAX_DIAGNOSTICS",
    "M0907_MAX_EVIDENCE",
    "M0907_MAX_PREDICTION_SET",
    "M0907_MAX_SCOPES",
    "M0907_MIN_COVERAGE",
    "M0907_MODULE_ID",
    "M0907_NOMINAL_COVERAGE",
    "M0907_OPERATION",
    "M0907_OUTPUT_MEDIA_TYPE",
    "M0907_OWNER",
    "M0907_PARENT",
    "M0907_PROVISIONAL_ABI",
    "M0907_SAFETY_CLASS",
    "M0907_UNCERTAINTY_MEDIA_TYPE",
    "CalibrateComplexActivitySelectivePredictionRequest",
    "CalibratedEstimate",
    "CalibrationConfiguration",
    "CalibrationDiagnostic",
    "CalibrationDiagnosticStatus",
    "CalibrationFindingCode",
    "CalibrationMethod",
    "CalibrationScope",
    "CalibrationStatus",
    "ComplexActivitySelectivePredictionResult",
    "PredictionSet",
]
