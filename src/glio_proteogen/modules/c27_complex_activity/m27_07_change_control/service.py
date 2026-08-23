"""Service and strict JSON boundary for M27-07."""

# ruff: noqa: TRY003

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m27_07 import (
    M2707_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityChangeControlResult,
    ControlComplexActivityChangeRequest,
)
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
            if isinstance(payload, bytes):
                strict_json_loads(payload, max_bytes=M2707_MAX_CANONICAL_REQUEST_BYTES)
                return ControlComplexActivityChangeRequest.model_validate_json(payload, strict=True)
            if isinstance(payload, str):
                strict_json_loads(payload, max_bytes=M2707_MAX_CANONICAL_REQUEST_BYTES)
                return ControlComplexActivityChangeRequest.model_validate_json(payload, strict=True)
            document: Any = json.dumps(payload, separators=(",", ":"))
            strict_json_loads(document, max_bytes=M2707_MAX_CANONICAL_REQUEST_BYTES)
            return ControlComplexActivityChangeRequest.model_validate_json(document, strict=True)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("M27-07 request validation failed") from error

    def execute(
        self, request: ControlComplexActivityChangeRequest
    ) -> ComplexActivityChangeControlResult:
        return self.engine.evaluate(request)

    def execute_json(
        self, payload: bytes | str | dict[str, Any]
    ) -> ComplexActivityChangeControlResult:
        return self.execute(self.validate_request(payload))

    def verify(
        self,
        result: ComplexActivityChangeControlResult,
        request: ControlComplexActivityChangeRequest | None = None,
    ) -> bool:
        try:
            if request is not None and result.request.model_dump(mode="json") != request.model_dump(
                mode="json"
            ):
                return False
            self.engine.replay(result)
        except ChangeControlReplayError:
            return False
        return True

    def replay(
        self,
        result: ComplexActivityChangeControlResult,
        request: ControlComplexActivityChangeRequest | None = None,
    ) -> ComplexActivityChangeControlResult:
        if request is not None and result.request.model_dump(mode="json") != request.model_dump(
            mode="json"
        ):
            raise ValueError("replay request mismatch")
        return self.engine.replay(result)


__all__ = ["M2707Service"]
