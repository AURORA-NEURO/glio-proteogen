"""Service and strict JSON boundary for M27-07."""

# ruff: noqa: TRY003, TRY301

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m27_07 import (
    M2707_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityChangeControlResult,
    ControlComplexActivityChangeRequest,
)
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
                if len(payload) > M2707_MAX_CANONICAL_REQUEST_BYTES:
                    raise ValueError("request exceeds canonical byte limit")
                document: Any = json.loads(payload)
            elif isinstance(payload, str):
                document = json.loads(payload)
            else:
                document = payload
            return ControlComplexActivityChangeRequest.model_validate(document, strict=True)
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
