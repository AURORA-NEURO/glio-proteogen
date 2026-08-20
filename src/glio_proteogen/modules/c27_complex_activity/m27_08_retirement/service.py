"""Strict service boundary for M27-08."""

# Public error text is intentionally sanitized and stable.
# ruff: noqa: TRY003, TRY301

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from glio_proteogen.contracts.m27_08 import (
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityRetirementResult,
    RetireComplexActivityServiceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.engine import (
    M2708RetirementEngine,
    RetirementReplayError,
)


class M2708Service:
    def __init__(self) -> None:
        self.engine = M2708RetirementEngine()

    def validate_request(
        self, payload: bytes | bytearray | str | Mapping[str, Any]
    ) -> RetireComplexActivityServiceRequest:
        try:
            decoded: object = {}
            if isinstance(payload, (bytes, bytearray, str)):
                decoded = strict_json_loads(payload, max_bytes=M2708_MAX_CANONICAL_REQUEST_BYTES)
                encoded = canonical_json_bytes(decoded)
            elif isinstance(payload, Mapping):
                encoded = canonical_json_bytes(dict(payload))
                strict_json_loads(encoded, max_bytes=M2708_MAX_CANONICAL_REQUEST_BYTES)
            else:
                raise TypeError("request must be JSON or a mapping")
            if not isinstance(decoded, dict):
                raise TypeError("request must be a JSON object")
            return RetireComplexActivityServiceRequest.model_validate_json(encoded, strict=True)
        except (StrictJsonError, ValueError, TypeError) as error:
            raise ValueError("M27-08 request validation failed") from error

    def execute(
        self, request: RetireComplexActivityServiceRequest
    ) -> ComplexActivityRetirementResult:
        return self.engine.evaluate(request)

    def execute_json(
        self, payload: bytes | str | dict[str, Any]
    ) -> ComplexActivityRetirementResult:
        return self.execute(self.validate_request(payload))

    def verify(self, result: ComplexActivityRetirementResult) -> bool:
        try:
            self.engine.replay(result)
        except RetirementReplayError:
            return False
        return True


__all__ = ["M2708Service"]
