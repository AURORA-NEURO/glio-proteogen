"""Strict M27-05 service seam."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_05 import (
    M2705_MAX_CANONICAL_REQUEST_BYTES,
    M2705_MAX_CANONICAL_RESULT_BYTES,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2705TelemetryEngine, preflight_m2705_authorization

_REQUEST_ADAPTER = TypeAdapter(EmitProteomicsTelemetryRequest)
_RESULT_ADAPTER = TypeAdapter(ProteomicsTelemetryResult)


class M2705Service:
    """Validate, emit, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2705TelemetryEngine | None = None) -> None:
        self._engine = engine or M2705TelemetryEngine()

    def validate_request(self, request: object) -> EmitProteomicsTelemetryRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2705_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2705_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        preflight_m2705_authorization(request)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(request)), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def emit(self, request: object) -> ProteomicsTelemetryResult:
        return self._engine.emit(self.validate_request(request))

    def replay(self, result: object) -> ProteomicsTelemetryResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2705_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(result, Mapping):
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(dict(result)), strict=True)
        else:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._engine.replay(typed)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M27-05",
            "operation": "emit_search_quant_observability_telemetry",
            "owner": "Data engineering",
            "safety_class": "S3",
            "gate": "G4",
            "parent": "complex activity",
            "provisional_abi": True,
            "telemetry_retention": True,
            "dashboards": True,
            "alert_states": True,
            "unsupported_to_negative": False,
            "biological_claims": False,
        }


__all__ = ["M2705Service"]
