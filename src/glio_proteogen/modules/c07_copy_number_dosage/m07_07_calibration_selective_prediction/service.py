"""Stateless application boundary for provisional M07-07."""

from glio_proteogen.contracts.m07_07 import (
    CalibrateSelectiveCopyNumberDosageRequest,
    CalibrateSelectiveCopyNumberDosageResult,
    canonical_request_digest,
    result_payload_digest,
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

    @staticmethod
    def verify_result(
        result: object,
        request: object | None = None,
    ) -> CalibrateSelectiveCopyNumberDosageResult:
        """Validate a replayed result and optionally bind it to a request."""

        typed = CalibrateSelectiveCopyNumberDosageResult.model_validate(result, strict=True)
        if request is not None:
            expected_request = M0707Service.validate_request(request)
            if typed.request_digest != canonical_request_digest(expected_request):
                raise ValueError("result request digest does not match replay request")  # noqa: TRY003
        if typed.result_digest != result_payload_digest(typed):
            raise ValueError("result digest does not match replay payload")  # noqa: TRY003
        return typed


__all__ = ["M0707Service"]
