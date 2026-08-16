"""Service seam for the provisional M22-07 operational evaluator."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_07 import (
    EvaluateProteinRnaDiscordanceHumanFactorsRequest,
    ProteinRnaDiscordanceHumanFactorsResult,
)

from .engine import M2207OperationalEngine, preflight_m2207_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinRnaDiscordanceHumanFactorsRequest)


class M2207Service:
    """Validate, evaluate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2207OperationalEngine | None = None) -> None:
        self._engine = engine or M2207OperationalEngine()

    def validate_request(self, request: object) -> EvaluateProteinRnaDiscordanceHumanFactorsRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2207_authorization(typed)
        return typed

    def evaluate(self, request: object) -> ProteinRnaDiscordanceHumanFactorsResult:
        return self._engine.generate(self.validate_request(request))

    def replay(
        self,
        result: ProteinRnaDiscordanceHumanFactorsResult,
    ) -> ProteinRnaDiscordanceHumanFactorsResult:
        return self._engine.replay(result)


__all__ = ["M2207Service"]
