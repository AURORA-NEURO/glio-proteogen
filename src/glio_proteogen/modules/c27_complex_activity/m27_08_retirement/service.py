"""Strict service boundary for M27-08."""

# ruff: noqa: TRY003

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m27_08 import (
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityRetirementResult,
    RetireComplexActivityServiceRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
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
                strict_json_loads(payload, max_bytes=M2708_MAX_CANONICAL_REQUEST_BYTES)
                return RetireComplexActivityServiceRequest.model_validate_json(payload, strict=True)
            if isinstance(payload, str):
                strict_json_loads(payload, max_bytes=M2708_MAX_CANONICAL_REQUEST_BYTES)
                return RetireComplexActivityServiceRequest.model_validate_json(payload, strict=True)
            document = json.dumps(payload, separators=(",", ":"))
            strict_json_loads(document, max_bytes=M2708_MAX_CANONICAL_REQUEST_BYTES)
            return RetireComplexActivityServiceRequest.model_validate_json(
                document, strict=True
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

    def verify(
        self,
        result: ComplexActivityRetirementResult,
        request: RetireComplexActivityServiceRequest | None = None,
    ) -> bool:
        try:
            if request is not None and result.request.model_dump(mode="json") != request.model_dump(
                mode="json"
            ):
                return False
            self.engine.replay(result)
        except RetirementReplayError:
            return False
        return True


__all__ = ["M2708Service"]
