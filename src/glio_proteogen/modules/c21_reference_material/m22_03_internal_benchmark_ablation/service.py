"""Service seam for the provisional M22-03 benchmark boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_03 import (
    ProteinRnaDiscordanceInternalBenchmarkResult,
    RunProteinRnaDiscordanceInternalBenchmarkRequest,
)

from .engine import M2203BenchmarkEngine, preflight_m2203_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(RunProteinRnaDiscordanceInternalBenchmarkRequest)


class M2203Service:
    """Validate, generate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2203BenchmarkEngine | None = None) -> None:
        self._engine = engine or M2203BenchmarkEngine()

    def validate_request(self, request: object) -> RunProteinRnaDiscordanceInternalBenchmarkRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2203_authorization(typed)
        return typed

    def generate(
        self,
        request: object,
    ) -> ProteinRnaDiscordanceInternalBenchmarkResult:
        return self._engine.generate(self.validate_request(request))

    def replay(
        self,
        result: ProteinRnaDiscordanceInternalBenchmarkResult,
    ) -> ProteinRnaDiscordanceInternalBenchmarkResult:
        return self._engine.replay(result)


__all__ = ["M2203Service"]
