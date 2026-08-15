"""Provisional M08-07 calibration and selective-prediction contracts.

The dossier specifies scoped calibration, support thresholds, OOD checks, and
abstention, but does not freeze the M08-06 handoff ABI, calibration method,
operation, endpoint, or media type.  This is reviewable scaffolding only.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m08_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
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
    UncertaintyEstimate,
    UncertaintyProfile,
)

M0807_MODULE_ID: Final = "GLIO-PROTEOGEN-M08-07"
M0807_OPERATION: Final = "calibrate_protein_subtype_selective_prediction"
M0807_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0807_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-07+json"
M0807_UNCERTAINTY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-06+json"
M0807_PARENT: Final = "protein_subtype"
M0807_OWNER: Final = "Clinical science"
M0807_SAFETY_CLASS: Final = "S2"
M0807_GATE: Final = "G3"
M0807_PROVISIONAL_ABI: Final = True
M0807_MAX_PREDICTION_SET: Final = 128
M0807_MAX_DIAGNOSTICS: Final = 128
M0807_MAX_EVIDENCE: Final = 64
M0807_MAX_SCOPES: Final = 64
M0807_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0807_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0807_NOMINAL_COVERAGE: Final = 0.9
M0807_EVIDENCE_CLAIM: Final = (
    "Caller-declared M08-06 uncertainty and calibration evidence; "
    "issuer authority is not authenticated."
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0807_MAX_EVIDENCE)


class CalibrationConfiguration(FrozenModel):
    """Locked calibration and selective support policy."""

    configuration_id: Identifier
    version: SemanticVersion
    method: CalibrationMethod
    scopes: tuple[CalibrationScope, ...] = Field(
        min_length=1,
        max_length=M0807_MAX_SCOPES,
    )
    nominal_coverage: float = Field(default=M0807_NOMINAL_COVERAGE, ge=0.0, le=1.0)
    support_threshold: float = Field(ge=0.0, le=1.0)
    ood_threshold: float = Field(ge=0.0, le=1.0)
    calibration_artifact: ArtifactReference
    benchmark_artifact: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0807_MAX_EVIDENCE)

    @model_validator(mode="after")
    def scopes_are_unique(self) -> CalibrationConfiguration:
        keys = tuple(
            (item.site, item.platform, item.disease_class, item.subgroup) for item in self.scopes
        )
        if len(keys) != len(set(keys)):
            raise ValueError("calibration scopes must be unique")
        return self


class CalibratedEstimate(FrozenModel):
    predicted_subtype: NonEmptyStr
    score: float = Field(ge=0.0, le=1.0)
    calibrated_confidence: float = Field(ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0807_MAX_EVIDENCE)


class PredictionSet(FrozenModel):
    labels: tuple[NonEmptyStr, ...] = Field(
        min_length=1,
        max_length=M0807_MAX_PREDICTION_SET,
    )
    nominal_coverage: float = Field(ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0807_MAX_EVIDENCE)

    @model_validator(mode="after")
    def labels_are_unique(self) -> PredictionSet:
        if len(self.labels) != len(set(self.labels)):
            raise ValueError("prediction-set labels must be unique")
        return self


class CalibrationDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: CalibrationDiagnosticStatus
    metric_name: NonEmptyStr
    metric_value: float | None = None
    subgroup: NonEmptyStr | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0807_MAX_EVIDENCE)


class CalibrateProteinSubtypeSelectivePredictionRequest(FrozenModel):
    """Provisional request bound to the complete M08-06 uncertainty result."""

    operation: Literal["calibrate_protein_subtype_selective_prediction"] = M0807_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0807_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    uncertainty_result: ArtifactReference
    configuration: CalibrationConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0807_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> CalibrateProteinSubtypeSelectivePredictionRequest:
        if self.uncertainty_result.media_type != M0807_UNCERTAINTY_MEDIA_TYPE:
            raise ValueError("calibration request must bind the provisional M08-06 result")
        if self.configuration.nominal_coverage != M0807_NOMINAL_COVERAGE:
            raise ValueError("provisional selective coverage target must be nominal 90 percent")
        return self


class ProteinSubtypeSelectivePredictionResult(FrozenModel):
    """Calibrated estimate, prediction set, and support decision with safe status."""

    output_type: Literal["protein_subtype_selective_prediction"] = (
        "protein_subtype_selective_prediction"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0807_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: CalibrateProteinSubtypeSelectivePredictionRequest
    status: CalibrationStatus
    estimate: CalibratedEstimate | None = None
    prediction_set: PredictionSet | None = None
    diagnostics: tuple[CalibrationDiagnostic, ...] = Field(
        min_length=1,
        max_length=M0807_MAX_DIAGNOSTICS,
    )
    findings: tuple[CalibrationFindingCode, ...] = Field(default=(), max_length=32)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M0807_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0807_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeSelectivePredictionResult:
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


def expected_uncertainty() -> UncertaintyProfile:
    """Return explicit non-estimable uncertainty for safe provisional abstention."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="The provisional M08-07 scaffold has no owner-confirmed calibration.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Selective coverage and subgroup disparity are not claimed before benchmark lock.",
        ),
    )


def expected_provenance(
    request: CalibrateProteinSubtypeSelectivePredictionRequest,
    request_digest: Sha256Digest,
    configuration_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project all seven caller controls into module-local provenance."""

    refs = request.context.references
    decisions = (
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
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0807_MODULE_ID,
        module_version=M0807_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request_digest, request.uncertainty_result.digest),
        configuration_digest=configuration_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M0807_CONTRACT_VERSION",
    "M0807_EVIDENCE_CLAIM",
    "M0807_GATE",
    "M0807_MAX_CANONICAL_REQUEST_BYTES",
    "M0807_MAX_CANONICAL_RESULT_BYTES",
    "M0807_MAX_DIAGNOSTICS",
    "M0807_MAX_EVIDENCE",
    "M0807_MAX_PREDICTION_SET",
    "M0807_MAX_SCOPES",
    "M0807_MODULE_ID",
    "M0807_NOMINAL_COVERAGE",
    "M0807_OPERATION",
    "M0807_OUTPUT_MEDIA_TYPE",
    "M0807_OWNER",
    "M0807_PARENT",
    "M0807_PROVISIONAL_ABI",
    "M0807_SAFETY_CLASS",
    "M0807_UNCERTAINTY_MEDIA_TYPE",
    "CalibrateProteinSubtypeSelectivePredictionRequest",
    "CalibratedEstimate",
    "CalibrationConfiguration",
    "CalibrationDiagnostic",
    "CalibrationDiagnosticStatus",
    "CalibrationFindingCode",
    "CalibrationMethod",
    "CalibrationScope",
    "CalibrationStatus",
    "PredictionSet",
    "ProteinSubtypeSelectivePredictionResult",
    "expected_provenance",
    "expected_uncertainty",
]
