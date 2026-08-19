"""Strict JSON service facade for M27-03."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_03 import (
    M2703_MAX_CANONICAL_REQUEST_BYTES,
    M2703_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivityPipelineResult,
    OrchestrateComplexActivityPipelineRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2703Engine, _plain_value

_REQUEST_ADAPTER = TypeAdapter(OrchestrateComplexActivityPipelineRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivityPipelineResult)


class M2703Service:
    """Parse-once service seam over the deterministic engine."""

    def __init__(self, engine: M2703Engine | None = None) -> None:
        self._engine = engine or M2703Engine()

    def validate_request(self, candidate: object) -> OrchestrateComplexActivityPipelineRequest:
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2703_MAX_CANONICAL_REQUEST_BYTES)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        if isinstance(candidate, Mapping):
            return _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(_plain_value(candidate)), strict=True
            )
        return self._engine.validate_request(candidate)

    def execute(self, request: object) -> ComplexActivityPipelineResult:
        return self._engine.execute(self.validate_request(request))

    def _execute_validated(
        self, request: OrchestrateComplexActivityPipelineRequest
    ) -> ComplexActivityPipelineResult:
        return self._engine.execute(request)

    def verify(self, result: object, *, replay: bool = True) -> ComplexActivityPipelineResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2703_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(result, Mapping):
            typed = _RESULT_ADAPTER.validate_json(
                canonical_json_bytes(
                    _plain_value(result, max_bytes=M2703_MAX_CANONICAL_RESULT_BYTES)
                ),
                strict=True,
            )
        else:
            typed = cast("ComplexActivityPipelineResult", result)
        return self._engine.verify(typed, replay=replay)


__all__ = ["M2703Service"]
