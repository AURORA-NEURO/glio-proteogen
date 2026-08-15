"""Deterministic, safe-abstaining provisional M08-07 calibration engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_07 import (
    M0807_CONTRACT_VERSION,
    M0807_EVIDENCE_CLAIM,
    M0807_PARENT,
    CalibrateProteinSubtypeSelectivePredictionRequest,
    CalibrationDiagnostic,
    CalibrationDiagnosticStatus,
    CalibrationFindingCode,
    CalibrationStatus,
    ProteinSubtypeSelectivePredictionResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m08_07.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateProteinSubtypeSelectivePredictionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeSelectivePredictionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0807AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M08-07 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0807_authorization(candidate: object) -> None:
    """Check controls before opening the complete M08-06 uncertainty handoff."""

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
        raise M0807AuthorizationError from None
    if states != expected:
        raise M0807AuthorizationError


def _evidence(
    request: CalibrateProteinSubtypeSelectivePredictionRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0807_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
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
                "The M08-07 ABI and subgroup calibration are provisional "
                "pending owner confirmation."
            ),
        ),
    )


class M0807CalibrationEngine:
    """Bind M08-06 and abstain until scoped calibration evidence is locked."""

    __slots__ = ()

    def calibrate(
        self,
        request: object,
    ) -> ProteinSubtypeSelectivePredictionResult:
        preflight_m0807_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        request_hash = canonical_request_digest(validated)
        configuration_hash = sha256_digest(validated.configuration)
        diagnostic = CalibrationDiagnostic(
            diagnostic_id=f"diagnostic.{request_hash.removeprefix('sha256:')}",
            status=CalibrationDiagnosticStatus.NOT_EVALUABLE,
            metric_name="selective_coverage",
            message=(
                "Owner-confirmed calibration, OOD thresholds, and subgroup evidence are not locked."
            ),
        )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0807_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": validated,
            "status": CalibrationStatus.ABSTAINED,
            "estimate": None,
            "prediction_set": None,
            "diagnostics": (diagnostic,),
            "findings": (CalibrationFindingCode.CALIBRATION_NOT_LOCKED,),
            "abstention_reason": diagnostic.message,
            "parent_target": M0807_PARENT,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0807_calibration_review_required",
                rationale=(
                    "Calibration error, selective coverage, and subgroup disparity require review."
                ),
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(validated, request_hash, configuration_hash),
            "evidence": _evidence(validated),
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ProteinSubtypeSelectivePredictionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def calibrate_protein_subtype_selective_prediction(
    request: object,
) -> ProteinSubtypeSelectivePredictionResult:
    """Public provisional M08-07 operation."""

    return M0807CalibrationEngine().calibrate(request)


__all__ = [
    "M0807AuthorizationError",
    "M0807CalibrationEngine",
    "calibrate_protein_subtype_selective_prediction",
    "preflight_m0807_authorization",
]
