"""Stateless application boundary for provisional M07-07."""

from glio_proteogen.contracts.m07_07 import (
    CalibrateSelectiveCopyNumberDosageRequest,
    CalibrateSelectiveCopyNumberDosageResult,
)

from .engine import (
    M0707CalibrationEngine,
    preflight_calibration_authorization,
)


class M0707Service:
    """Authorize, strictly validate, and execute one M07-07 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0707CalibrationEngine | None = None) -> None:
        self._engine = engine or M0707CalibrationEngine()

    @staticmethod
    def validate_request(request: object) -> CalibrateSelectiveCopyNumberDosageRequest:
        preflight_calibration_authorization(request)
        return CalibrateSelectiveCopyNumberDosageRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: CalibrateSelectiveCopyNumberDosageRequest,
    ) -> CalibrateSelectiveCopyNumberDosageResult:
        return self._engine.calibrate(request)

    def execute(self, request: object) -> CalibrateSelectiveCopyNumberDosageResult:
        return self._engine.calibrate(request)


__all__ = ["M0707Service"]
