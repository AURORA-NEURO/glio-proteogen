"""Strict service seam for M26-05 observability and replay."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_05 import (
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry.engine import (
    M2605ObservabilityEngine,
    M2605ReplayError,
    preflight_m2605_authorization,
    verify_telemetry_result,
)

_REQUEST_ADAPTER: Final[TypeAdapter[EmitProteomicsTelemetryRequest]] = TypeAdapter(
    EmitProteomicsTelemetryRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteomicsTelemetryResult]] = TypeAdapter(
    ProteomicsTelemetryResult
)


class M2605ObservabilityService:
    """Validate, emit, and replay one M26-05 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2605ObservabilityEngine | None = None) -> None:
        self._engine = engine or M2605ObservabilityEngine()

    @staticmethod
    def validate_request(request: object) -> EmitProteomicsTelemetryRequest:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2605_authorization(validated)
        return validated

    def execute(self, request: object) -> ProteomicsTelemetryResult:
        return self._engine.emit(self.validate_request(request))

    @staticmethod
    def verify(result: object) -> ProteomicsTelemetryResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except ValidationError as error:
            raise M2605ReplayError from error
        return verify_telemetry_result(validated)


__all__ = ["M2605ObservabilityService"]
