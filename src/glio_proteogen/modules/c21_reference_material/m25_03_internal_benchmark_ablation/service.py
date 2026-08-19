"""Service seam for the provisional M25-03 benchmark boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_03 import (
    M2503_MAX_CANONICAL_REQUEST_BYTES,
    ProteotypeInternalBenchmarkResult,
    RunProteotypeInternalBenchmarkRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2503BenchmarkEngine, preflight_m2503_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(RunProteotypeInternalBenchmarkRequest)


class M2503Service:
    """Validate, execute, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2503BenchmarkEngine | None = None) -> None:
        self._engine = engine or M2503BenchmarkEngine()

    def validate_request(self, request: object) -> RunProteotypeInternalBenchmarkRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M2503_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
            preflight_m2503_authorization(typed)
        else:
            preflight_m2503_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return typed

    def execute(self, request: object) -> ProteotypeInternalBenchmarkResult:
        return self._engine.generate(self.validate_request(request))

    def verify_replay(
        self,
        result: ProteotypeInternalBenchmarkResult,
    ) -> ProteotypeInternalBenchmarkResult:
        return self._engine.replay(result)


__all__ = ["M2503Service"]
