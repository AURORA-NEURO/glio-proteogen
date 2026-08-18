"""Strict service boundary for M27-08."""

# Public error text is intentionally sanitized and stable.
# ruff: noqa: TRY003, TRY301

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m27_08 import (
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityRetirementResult,
    RetireComplexActivityServiceRequest,
)
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.engine import (
    M2708RetirementEngine,
    RetirementReplayError,
)


class M2708Service:
    def __init__(self) -> None:
        self.engine = M2708RetirementEngine()

    def validate_request(
        self, payload: bytes | str | dict[str, Any]
    ) -> RetireComplexActivityServiceRequest:
        try:
            if isinstance(payload, bytes):
                if len(payload) > M2708_MAX_CANONICAL_REQUEST_BYTES:
                    raise ValueError("request exceeds canonical byte limit")
                return RetireComplexActivityServiceRequest.model_validate_json(payload, strict=True)
            if isinstance(payload, str):
                return RetireComplexActivityServiceRequest.model_validate_json(payload, strict=True)
            return RetireComplexActivityServiceRequest.model_validate_json(
                json.dumps(payload, separators=(",", ":")), strict=True
            )
        except (ValueError, TypeError, json.JSONDecodeError) as error:
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
