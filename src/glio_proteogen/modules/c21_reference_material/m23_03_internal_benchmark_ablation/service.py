"""Service seam for the provisional M23-03 benchmark boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_03 import (
    RunVariantPeptideInternalBenchmarkRequest,
    VariantPeptideInternalBenchmarkResult,
)

from .engine import M2303BenchmarkEngine, preflight_m2303_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(RunVariantPeptideInternalBenchmarkRequest)


class M2303Service:
    """Validate, generate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2303BenchmarkEngine | None = None) -> None:
        self._engine = engine or M2303BenchmarkEngine()

    def validate_request(self, request: object) -> RunVariantPeptideInternalBenchmarkRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2303_authorization(typed)
        return typed

    def generate(self, request: object) -> VariantPeptideInternalBenchmarkResult:
        return self._engine.generate(self.validate_request(request))

    def replay(
        self,
        result: VariantPeptideInternalBenchmarkResult,
    ) -> VariantPeptideInternalBenchmarkResult:
        return self._engine.replay(result)


__all__ = ["M2303Service"]
