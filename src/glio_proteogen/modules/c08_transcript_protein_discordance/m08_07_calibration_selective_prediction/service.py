"""Stateless application boundary for provisional M08-07."""

from __future__ import annotations

import json
from typing import Any

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_07 import (
    CalibrateProteinSubtypeSelectivePredictionRequest,
    ProteinSubtypeSelectivePredictionResult,
    verify_result_replay,
)

from .engine import M0807CalibrationEngine, preflight_m0807_authorization


def _json_default(value: object) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    raise TypeError(f"unsupported request value: {type(value).__name__}")


class M0807Service:
    """Authorize, strictly validate, and execute one M08-07 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0807CalibrationEngine | None = None) -> None:
        self._engine = engine or M0807CalibrationEngine()

    @staticmethod
    def validate_request(request: object) -> CalibrateProteinSubtypeSelectivePredictionRequest:
        preflight_m0807_authorization(request)
        if isinstance(request, dict):
            # JSON encodings use strings for enum/datetime values and arrays for
            # tuples.  Pydantic's JSON strict mode accepts those representations
            # while still rejecting Python-side coercions.
            return CalibrateProteinSubtypeSelectivePredictionRequest.model_validate_json(
                json.dumps(
                    request,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=_json_default,
                ),
                strict=True,
            )
        return CalibrateProteinSubtypeSelectivePredictionRequest.model_validate(
            request,
            strict=True,
        )

    def _execute_validated(
        self,
        request: CalibrateProteinSubtypeSelectivePredictionRequest,
    ) -> ProteinSubtypeSelectivePredictionResult:
        return self._engine.calibrate(request)

    def execute(self, request: object) -> ProteinSubtypeSelectivePredictionResult:
        return self._engine.calibrate(self.validate_request(request))

    @staticmethod
    def verify(
        result: object,
        request: object | None = None,
    ) -> bool:
        """Validate a result and verify its canonical request/result digests."""

        try:
            typed_result = TypeAdapter(ProteinSubtypeSelectivePredictionResult).validate_python(
                result,
                strict=True,
            )
            typed_request = None
            if request is not None:
                typed_request = CalibrateProteinSubtypeSelectivePredictionRequest.model_validate(
                    request,
                    strict=True,
                )
            return verify_result_replay(typed_result, typed_request)
        except (TypeError, ValueError):
            return False


__all__ = ["M0807Service"]
