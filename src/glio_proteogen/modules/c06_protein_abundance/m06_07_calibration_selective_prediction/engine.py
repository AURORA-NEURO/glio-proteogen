"""Provisional M06-07 calibration/selective-prediction boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_07 import CalibrateSelectiveProteinAbundanceRequest
from glio_proteogen.kernel.models import ConsentState, IdentityLineageState, UpstreamDecisionState

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateSelectiveProteinAbundanceRequest)


class CalibrationAuthorizationError(PermissionError):
    """Raised before an unauthorized calibration request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M06-07 calibration request is not authorized")


class CalibrationInputError(ValueError):
    """Raised for a structurally valid request outside the provisional envelope."""


def preflight_calibration_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates when typed."""

    if not isinstance(request, CalibrateSelectiveProteinAbundanceRequest):
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


class M0607CalibrationEngine:
    """Import-safe calibration seam; metrics and calibration execution are not frozen."""

    @staticmethod
    def validate_request(request: object) -> CalibrateSelectiveProteinAbundanceRequest:
        preflight_calibration_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def calibrate(self, request: object) -> None:
        self.validate_request(request)
        raise NotImplementedError(
            "M06-07 calibration awaits ABI, subgroup metrics, and coverage freeze"
        )


def calibrate_selective_protein_abundance(request: object) -> None:
    return M0607CalibrationEngine().calibrate(request)


__all__ = [
    "CalibrationAuthorizationError",
    "CalibrationInputError",
    "M0607CalibrationEngine",
    "calibrate_selective_protein_abundance",
    "preflight_calibration_authorization",
]
