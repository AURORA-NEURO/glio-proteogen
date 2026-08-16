"""Service seam for the provisional M25-03 benchmark boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_03 import (
    ProteotypeInternalBenchmarkResult,
    RunProteotypeInternalBenchmarkRequest,
)

from .engine import M2503BenchmarkEngine, preflight_m2503_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(RunProteotypeInternalBenchmarkRequest)


class M2503Service:
    """Validate, execute, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2503BenchmarkEngine | None = None) -> None:
        self._engine = engine or M2503BenchmarkEngine()

    def validate_request(self, request: object) -> RunProteotypeInternalBenchmarkRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2503_authorization(typed)
        return typed

    def execute(self, request: object) -> ProteotypeInternalBenchmarkResult:
        return self._engine.generate(self.validate_request(request))

    def verify_replay(
        self,
        result: ProteotypeInternalBenchmarkResult,
    ) -> ProteotypeInternalBenchmarkResult:
        return self._engine.replay(result)


__all__ = ["M2503Service"]
