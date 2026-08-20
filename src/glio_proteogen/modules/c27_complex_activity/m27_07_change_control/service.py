"""Service and strict JSON boundary for M27-07."""

# ruff: noqa: TRY003, TRY301

from __future__ import annotations

from typing import Any

from glio_proteogen.contracts.m27_07 import (
    M2707_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityChangeControlResult,
    ControlComplexActivityChangeRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.engine import (
    ChangeControlReplayError,
    M2707ChangeControlEngine,
)


class M2707Service:
    """Validated request execution and replay service."""

    def __init__(self) -> None:
        self.engine = M2707ChangeControlEngine()

    def validate_request(
        self, payload: bytes | str | dict[str, Any]
    ) -> ControlComplexActivityChangeRequest:
        try:
            encoded: bytes | str
            if isinstance(payload, dict):
                encoded = canonical_json_bytes(payload)
            elif isinstance(payload, (bytes, str)):
                encoded = payload
            else:
                raise TypeError("request must be JSON or a mapping")
            decoded = strict_json_loads(
                encoded,
                max_bytes=M2707_MAX_CANONICAL_REQUEST_BYTES,
            )
            if not isinstance(decoded, dict):
                raise TypeError("request must be a JSON object")
            return ControlComplexActivityChangeRequest.model_validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        except (ValueError, TypeError) as error:
            raise ValueError("M27-07 request validation failed") from error

    def execute(
        self, request: ControlComplexActivityChangeRequest
    ) -> ComplexActivityChangeControlResult:
        return self.engine.evaluate(request)

    def execute_json(
        self, payload: bytes | str | dict[str, Any]
    ) -> ComplexActivityChangeControlResult:
        return self.execute(self.validate_request(payload))

    def verify(self, result: ComplexActivityChangeControlResult) -> bool:
        try:
            self.engine.replay(result)
        except ChangeControlReplayError:
            return False
        return True

    def replay(
        self, result: ComplexActivityChangeControlResult
    ) -> ComplexActivityChangeControlResult:
        return self.engine.replay(result)


__all__ = ["M2707Service"]
