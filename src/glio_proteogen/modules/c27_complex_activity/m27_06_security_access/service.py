"""Strict M27-06 service seam."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_06 import (
    M2706_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivitySecurityAccessResult,
    EvaluateComplexActivitySecurityAccessRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2706SecurityEngine, preflight_m2706_authorization

_REQUEST_ADAPTER = TypeAdapter(EvaluateComplexActivitySecurityAccessRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivitySecurityAccessResult)


class M2706Service:
    """Validate, evaluate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2706SecurityEngine | None = None) -> None:
        self._engine = engine or M2706SecurityEngine()

    def validate_request(self, request: object) -> EvaluateComplexActivitySecurityAccessRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2706_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        preflight_m2706_authorization(request)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(request)), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def emit(self, request: object) -> ComplexActivitySecurityAccessResult:
        return self._engine.emit(self.validate_request(request))

    def replay(self, result: object) -> ComplexActivitySecurityAccessResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(result, Mapping):
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(dict(result)), strict=True)
        else:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._engine.replay(typed)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M27-06",
            "operation": "evaluate_complex_activity_security_access",
            "owner": "Platform engineering",
            "safety_class": "S3",
            "gate": "G4",
            "parent": "complex activity",
            "provisional_abi": True,
            "unsupported_to_negative": False,
            "biological_claims": False,
        }


__all__ = ["M2706Service"]
