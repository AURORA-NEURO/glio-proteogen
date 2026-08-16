"""Deterministic, safe-abstaining provisional M09-07 calibration engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_07 import (
    M0907_CONTRACT_VERSION,
    M0907_COVERAGE_CEILING,
    M0907_COVERAGE_FLOOR,
    M0907_EVIDENCE_CLAIM,
    M0907_PARENT,
    CalibrateComplexActivitySelectivePredictionRequest,
    CalibratedEstimate,
    CalibrationDiagnostic,
    CalibrationDiagnosticStatus,
    CalibrationFindingCode,
    CalibrationStatus,
    ComplexActivitySelectivePredictionResult,
    PredictionSet,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m09_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateComplexActivitySelectivePredictionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivitySelectivePredictionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0907AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M09-07 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0907_authorization(candidate: object) -> None:
    """Check controls before opening the complete M09-06 uncertainty handoff."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M0907AuthorizationError from None
    if states != expected:
        raise M0907AuthorizationError


def _evidence(
    request: CalibrateComplexActivitySelectivePredictionRequest,
) -> tuple[EvidenceReference, ...]:
    refs = list(request.source_artifacts)
    if request.candidate is not None:
        refs.extend(item.reference for item in request.candidate.evidence)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0907_EVIDENCE_CLAIM)
        for artifact in refs
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="calibration_selective_prediction_only",
            statement=(
                "Output is limited to calibrated estimate, prediction set, and support decision."
            ),
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no kinase state, treatment recommendation, or parent subtype."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M09-07 ABI and subgroup calibration are provisional "
                "pending owner confirmation."
            ),
        ),
    )


class M0907CalibrationEngine:
    """Bind M09-06 and abstain until scoped calibration evidence is locked."""

    __slots__ = ()

    def calibrate(  # noqa: PLR0915
        self,
        request: object,
    ) -> ComplexActivitySelectivePredictionResult:
        preflight_m0907_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        request_hash = canonical_request_digest(validated)
        configuration_hash = sha256_digest(validated.configuration)
        candidate = validated.candidate
        diagnostics: list[CalibrationDiagnostic] = []
        findings: list[CalibrationFindingCode] = []
        estimate: CalibratedEstimate | None = None
        prediction_set: PredictionSet | None = None
        status = CalibrationStatus.CALIBRATED
        support_status = SupportStatus.SUPPORTED
        support_reason = "m0907_calibration_supported"
        support_rationale = "Candidate passed scope, support, OOD, coverage, and disparity gates."
        abstention_reason: str | None = None

        def add_metric(
            name: str,
            value: float,
            message: str,
            *,
            diagnostic_status: CalibrationDiagnosticStatus,
        ) -> None:
            diagnostics.append(
                CalibrationDiagnostic(
                    diagnostic_id=(
                        f"diagnostic.{request_hash.removeprefix('sha256:')}.{len(diagnostics)}"
                    ),
                    status=diagnostic_status,
                    metric_name=name,
                    metric_value=value,
                    message=message,
                )
            )

        def abstain(
            finding: CalibrationFindingCode,
            reason: str,
            *,
            hard_unsupported: bool,
        ) -> None:
            nonlocal status, support_status, support_reason, support_rationale, abstention_reason
            status = CalibrationStatus.ABSTAINED
            support_status = (
                SupportStatus.UNSUPPORTED if hard_unsupported else SupportStatus.REVIEW_REQUIRED
            )
            support_reason = "m0907_unsupported" if hard_unsupported else "m0907_review_required"
            support_rationale = reason
            abstention_reason = reason
            findings.append(finding)

        if candidate is None:
            diagnostics.append(
                CalibrationDiagnostic(
                    diagnostic_id=f"diagnostic.{request_hash.removeprefix('sha256:')}.0",
                    status=CalibrationDiagnosticStatus.NOT_EVALUABLE,
                    metric_name="selective_coverage",
                    message=(
                        "No caller-declared candidate was supplied; calibration evidence "
                        "is not evaluable."
                    ),
                )
            )
            abstain(
                CalibrationFindingCode.MISSING_CANDIDATE,
                "Calibration requires a caller-declared candidate and locked evidence.",
                hard_unsupported=False,
            )
        else:
            configured_scopes = {
                (item.site, item.platform, item.disease_class, item.subgroup)
                for item in validated.configuration.scopes
            }
            candidate_scope = (
                candidate.site,
                candidate.platform,
                candidate.disease_class,
                candidate.subgroup,
            )
            if candidate_scope not in configured_scopes:
                add_metric(
                    "scope_support",
                    0.0,
                    "Candidate scope is not covered by the locked calibration configuration.",
                    diagnostic_status=CalibrationDiagnosticStatus.FAIL,
                )
                abstain(
                    CalibrationFindingCode.SCOPE_NOT_SUPPORTED,
                    "Candidate scope is not covered by the locked calibration configuration.",
                    hard_unsupported=True,
                )
            elif candidate.support_score < validated.configuration.support_threshold:
                add_metric(
                    "support_score",
                    candidate.support_score,
                    "Candidate support score is below the configured threshold.",
                    diagnostic_status=CalibrationDiagnosticStatus.FAIL,
                )
                abstain(
                    CalibrationFindingCode.SUPPORT_THRESHOLD_NOT_MET,
                    "Candidate support score did not meet the configured threshold.",
                    hard_unsupported=True,
                )
            elif candidate.ood_score > validated.configuration.ood_threshold:
                add_metric(
                    "ood_score",
                    candidate.ood_score,
                    "Candidate OOD score exceeds the configured threshold.",
                    diagnostic_status=CalibrationDiagnosticStatus.FAIL,
                )
                abstain(
                    CalibrationFindingCode.OOD_UNSUPPORTED,
                    "Candidate is outside the configured support domain.",
                    hard_unsupported=True,
                )
            elif not (
                M0907_COVERAGE_FLOOR <= candidate.observed_coverage <= M0907_COVERAGE_CEILING
            ):
                add_metric(
                    "selective_coverage",
                    candidate.observed_coverage,
                    "Observed coverage is outside the provisional 85%-95% acceptance envelope.",
                    diagnostic_status=CalibrationDiagnosticStatus.FAIL,
                )
                abstain(
                    CalibrationFindingCode.COVERAGE_OUT_OF_BOUNDS,
                    "Observed selective coverage is outside the acceptance envelope.",
                    hard_unsupported=False,
                )
            elif candidate.calibration_error > validated.configuration.calibration_error_ceiling:
                add_metric(
                    "calibration_error",
                    candidate.calibration_error,
                    "Calibration error exceeds the configured ceiling.",
                    diagnostic_status=CalibrationDiagnosticStatus.FAIL,
                )
                abstain(
                    CalibrationFindingCode.CALIBRATION_ERROR_EXCEEDED,
                    "Calibration error did not meet the configured ceiling.",
                    hard_unsupported=False,
                )
            elif candidate.subgroup_disparity > validated.configuration.subgroup_disparity_ceiling:
                add_metric(
                    "subgroup_disparity",
                    candidate.subgroup_disparity,
                    "Subgroup disparity exceeds the configured ceiling.",
                    diagnostic_status=CalibrationDiagnosticStatus.FAIL,
                )
                abstain(
                    CalibrationFindingCode.SUBGROUP_DISPARITY,
                    "Subgroup disparity requires review before calibrated release.",
                    hard_unsupported=False,
                )
            else:
                add_metric(
                    "selective_coverage",
                    candidate.observed_coverage,
                    "Observed coverage meets the provisional acceptance envelope.",
                    diagnostic_status=CalibrationDiagnosticStatus.PASS,
                )
                add_metric(
                    "calibration_error",
                    candidate.calibration_error,
                    "Calibration error meets the configured ceiling.",
                    diagnostic_status=CalibrationDiagnosticStatus.PASS,
                )
                add_metric(
                    "subgroup_disparity",
                    candidate.subgroup_disparity,
                    "Subgroup disparity meets the configured ceiling.",
                    diagnostic_status=CalibrationDiagnosticStatus.PASS,
                )
                estimate = CalibratedEstimate(
                    predicted_subtype=candidate.predicted_subtype,
                    score=candidate.score,
                    calibrated_confidence=candidate.calibrated_confidence,
                    calibration_reference=validated.configuration.calibration_artifact,
                    evidence=candidate.evidence,
                )
                prediction_set = PredictionSet(
                    labels=candidate.labels,
                    nominal_coverage=validated.configuration.nominal_coverage,
                    evidence=candidate.evidence,
                )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0907_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": validated,
            "status": status,
            "estimate": estimate,
            "prediction_set": prediction_set,
            "diagnostics": tuple(diagnostics),
            "findings": tuple(findings),
            "abstention_reason": abstention_reason,
            "parent_target": M0907_PARENT,
            "support_decision": SupportDecision(
                status=support_status,
                reason_code=support_reason,
                rationale=support_rationale,
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(validated, request_hash, configuration_hash),
            "evidence": _evidence(validated),
            "limitations": _limitations(),
            "human_review_required": status is CalibrationStatus.ABSTAINED,
        }
        constructed = ComplexActivitySelectivePredictionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def calibrate_complex_activity_selective_prediction(
    request: object,
) -> ComplexActivitySelectivePredictionResult:
    """Public provisional M09-07 operation."""

    return M0907CalibrationEngine().calibrate(request)


__all__ = [
    "M0907AuthorizationError",
    "M0907CalibrationEngine",
    "calibrate_complex_activity_selective_prediction",
    "preflight_m0907_authorization",
]
