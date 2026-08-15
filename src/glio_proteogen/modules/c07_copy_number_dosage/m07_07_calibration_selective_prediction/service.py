"""Stateless application boundary for provisional M07-07."""

from typing import cast

from pydantic import TypeAdapter

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

_REQUEST_ADAPTER = TypeAdapter(CalibrateSelectiveCopyNumberDosageRequest)
_RESULT_ADAPTER = TypeAdapter(CalibrateSelectiveCopyNumberDosageResult)


class M0707Service:
    """Authorize, strictly validate, and execute one M07-07 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0707CalibrationEngine | None = None) -> None:
        self._engine = engine or M0707CalibrationEngine()

    @staticmethod
    def validate_request(request: object) -> CalibrateSelectiveCopyNumberDosageRequest:
        if type(request) in {bytes, bytearray, str}:
            typed = _REQUEST_ADAPTER.validate_json(
                cast("str | bytes | bytearray", request), strict=True
            )
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_calibration_authorization(typed)
        return typed

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

        if type(result) in {bytes, bytearray, str}:
            typed = _RESULT_ADAPTER.validate_json(
                cast("str | bytes | bytearray", result), strict=True
            )
        else:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        if request is not None:
            expected_request = M0707Service.validate_request(request)
            if typed.request_digest != canonical_request_digest(expected_request):
                raise ValueError("result request digest does not match replay request")  # noqa: TRY003
        if typed.result_digest != result_payload_digest(typed):
            raise ValueError("result digest does not match replay payload")  # noqa: TRY003
        return typed


__all__ = ["M0707Service"]
