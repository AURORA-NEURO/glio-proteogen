"""Service seam for the provisional M24-03 benchmark boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_03 import (
    BiomarkerPanelInternalBenchmarkResult,
    RunBiomarkerPanelInternalBenchmarkRequest,
)

from .engine import M2403BenchmarkEngine, preflight_m2403_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(RunBiomarkerPanelInternalBenchmarkRequest)


class M2403Service:
    """Validate, generate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2403BenchmarkEngine | None = None) -> None:
        self._engine = engine or M2403BenchmarkEngine()

    def validate_request(self, request: object) -> RunBiomarkerPanelInternalBenchmarkRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2403_authorization(typed)
        return typed

    def generate(self, request: object) -> BiomarkerPanelInternalBenchmarkResult:
        return self._engine.generate(self.validate_request(request))

    def replay(
        self,
        result: BiomarkerPanelInternalBenchmarkResult,
    ) -> BiomarkerPanelInternalBenchmarkResult:
        return self._engine.replay(result)


__all__ = ["M2403Service"]
