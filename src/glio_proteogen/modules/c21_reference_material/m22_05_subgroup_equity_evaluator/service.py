"""Service seam for the provisional M22-05 subgroup evaluator."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_05 import (
    EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
    ProteinRnaDiscordanceSubgroupEvaluationResult,
)

from .engine import M2205EquityEngine, preflight_m2205_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinRnaDiscordanceSubgroupEquityRequest)


class M2205Service:
    """Validate, evaluate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2205EquityEngine | None = None) -> None:
        self._engine = engine or M2205EquityEngine()

    def validate_request(
        self, request: object
    ) -> EvaluateProteinRnaDiscordanceSubgroupEquityRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2205_authorization(typed)
        return typed

    def evaluate(self, request: object) -> ProteinRnaDiscordanceSubgroupEvaluationResult:
        return self._engine.generate(self.validate_request(request))

    def replay(
        self,
        result: ProteinRnaDiscordanceSubgroupEvaluationResult,
    ) -> ProteinRnaDiscordanceSubgroupEvaluationResult:
        return self._engine.replay(result)


__all__ = ["M2205Service"]
