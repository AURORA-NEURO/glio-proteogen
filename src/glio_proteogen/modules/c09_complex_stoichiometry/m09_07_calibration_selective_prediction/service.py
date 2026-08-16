"""Stateless application boundary for provisional M09-07."""

from __future__ import annotations

import json

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_07 import (
    CalibrateComplexActivitySelectivePredictionRequest,
    ComplexActivitySelectivePredictionResult,
    verify_result_replay,
)

from .engine import M0907CalibrationEngine, preflight_m0907_authorization


def _json_default(value: object) -> object:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    raise TypeError from None


class M0907Service:
    """Authorize, strictly validate, and execute one M09-07 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0907CalibrationEngine | None = None) -> None:
        self._engine = engine or M0907CalibrationEngine()

    @staticmethod
    def validate_request(request: object) -> CalibrateComplexActivitySelectivePredictionRequest:
        preflight_m0907_authorization(request)
        if isinstance(request, dict):
            # JSON encodings use strings for enum/datetime values and arrays for
            # tuples.  Pydantic's JSON strict mode accepts those representations
            # while still rejecting Python-side coercions.
            return CalibrateComplexActivitySelectivePredictionRequest.model_validate_json(
                json.dumps(
                    request,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=_json_default,
                ),
                strict=True,
            )
        return CalibrateComplexActivitySelectivePredictionRequest.model_validate(
            request,
            strict=True,
        )

    def _execute_validated(
        self,
        request: CalibrateComplexActivitySelectivePredictionRequest,
    ) -> ComplexActivitySelectivePredictionResult:
        return self._engine.calibrate(request)

    def execute(self, request: object) -> ComplexActivitySelectivePredictionResult:
        return self._engine.calibrate(self.validate_request(request))

    @staticmethod
    def verify(
        result: object,
        request: object | None = None,
    ) -> bool:
        """Validate a result and verify its canonical request/result digests."""

        try:
            result_adapter = TypeAdapter(ComplexActivitySelectivePredictionResult)
            if isinstance(result, dict):
                typed_result = result_adapter.validate_json(
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    strict=True,
                )
            else:
                typed_result = result_adapter.validate_python(result, strict=True)
            typed_request = None
            if request is not None:
                if isinstance(request, dict):
                    typed_request = (
                        CalibrateComplexActivitySelectivePredictionRequest.model_validate_json(
                            json.dumps(request, ensure_ascii=False, separators=(",", ":")),
                            strict=True,
                        )
                    )
                else:
                    typed_request = (
                        CalibrateComplexActivitySelectivePredictionRequest.model_validate(
                            request,
                            strict=True,
                        )
                    )
            return verify_result_replay(typed_result, typed_request)
        except (TypeError, ValueError):
            return False


__all__ = ["M0907Service"]
