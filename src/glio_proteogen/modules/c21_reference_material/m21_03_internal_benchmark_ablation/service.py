"""Service seam for the provisional M21-03 benchmark boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_03 import (
    ComplexActivityInternalBenchmarkResult,
    RunComplexActivityInternalBenchmarkRequest,
)

from .engine import M2103Engine, preflight_m2103_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(RunComplexActivityInternalBenchmarkRequest)


class M2103Service:
    """Validate, generate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2103Engine | None = None) -> None:
        self._engine = engine or M2103Engine()

    def validate_request(self, request: object) -> RunComplexActivityInternalBenchmarkRequest:
        preflight_m2103_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def generate(
        self,
        request: RunComplexActivityInternalBenchmarkRequest,
    ) -> ComplexActivityInternalBenchmarkResult:
        return self._engine.generate(request)

    def replay(
        self,
        result: ComplexActivityInternalBenchmarkResult,
    ) -> ComplexActivityInternalBenchmarkResult:
        return self._engine.replay(result)


__all__ = ["M2103Service"]
