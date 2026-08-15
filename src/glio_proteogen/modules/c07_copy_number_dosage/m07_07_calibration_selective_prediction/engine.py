"""Provisional M07-07 calibration/selective-prediction boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_07 import (
    CalibrateSelectiveCopyNumberDosageRequest,
    CalibrateSelectiveCopyNumberDosageResult,
)
from glio_proteogen.kernel.models import ConsentState, IdentityLineageState, UpstreamDecisionState

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateSelectiveCopyNumberDosageRequest)


class CalibrationAuthorizationError(PermissionError):
    """Raised before an unauthorized calibration request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M07-07 calibration request is not authorized")


class CalibrationInputError(ValueError):
    """Raised for a structurally valid request outside the provisional envelope."""


def preflight_calibration_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates when typed."""

    if not isinstance(request, CalibrateSelectiveCopyNumberDosageRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise CalibrationAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise CalibrationAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise CalibrationAuthorizationError


class M0707CalibrationEngine:
    """Import-safe calibration seam; metrics are not dossier-frozen yet."""

    @staticmethod
    def validate_request(request: object) -> CalibrateSelectiveCopyNumberDosageRequest:
        preflight_calibration_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def calibrate(self, request: object) -> CalibrateSelectiveCopyNumberDosageResult:
        self.validate_request(request)
        raise NotImplementedError(
            "M07-07 calibration awaits ABI, subgroup metrics, and coverage freeze"
        )


def calibrate_selective_copy_number_dosage(
    request: object,
) -> CalibrateSelectiveCopyNumberDosageResult:
    return M0707CalibrationEngine().calibrate(request)


__all__ = [
    "CalibrationAuthorizationError",
    "CalibrationInputError",
    "M0707CalibrationEngine",
    "calibrate_selective_copy_number_dosage",
    "preflight_calibration_authorization",
]
