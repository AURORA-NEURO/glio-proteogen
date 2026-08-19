"""Typed service facade for the provisional M26-03 orchestrator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_03 import (
    M2603_MAX_CANONICAL_REQUEST_BYTES,
    M2603_MAX_CANONICAL_RESULT_BYTES,
    ExecuteProteinSubtypeWorkflowRequest,
    ProteinSubtypeExecutionResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2603Engine, preflight_m2603_authorization

_REQUEST_ADAPTER = TypeAdapter(ExecuteProteinSubtypeWorkflowRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeExecutionResult)


class M2603Service:
    """Stable parse-once service seam over the stateless execution engine."""

    def __init__(self, engine: M2603Engine | None = None) -> None:
        self._engine = engine or M2603Engine()

    def validate_request(self, candidate: object) -> ExecuteProteinSubtypeWorkflowRequest:
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2603_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2603_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        if isinstance(candidate, Mapping):
            preflight_m2603_authorization(candidate)
            return _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(dict(candidate)), strict=True
            )
        return self._engine.validate_request(candidate)

    def execute(self, request: object) -> ProteinSubtypeExecutionResult:
        return self._engine.execute(self.validate_request(request))

    def _execute_validated(
        self, request: ExecuteProteinSubtypeWorkflowRequest
    ) -> ProteinSubtypeExecutionResult:
        return self._engine.execute(request)

    def verify(self, result: object, *, replay: bool = True) -> ProteinSubtypeExecutionResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2603_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(result, Mapping):
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(dict(result)), strict=True)
        else:
            typed = cast("ProteinSubtypeExecutionResult", result)
        return self._engine.verify(typed, replay=replay)


__all__ = ["M2603Service"]
