"""Service boundary for provisional M15-02 replay."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m15_02 import (
    LongitudinalRecurrenceContextStratificationResult,
    StratifyContextAndSubtypeRequest,
)

from .engine import M1502ContextStratifierEngine, infer_context_and_subtype


class _InvalidM1502RequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-02 request must be a strict request model or mapping")


class M1502Service:
    """Validate and execute M15-02 through one stateless service object."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1502ContextStratifierEngine()

    def validate_request(self, candidate: object) -> StratifyContextAndSubtypeRequest:
        if type(candidate) is StratifyContextAndSubtypeRequest:
            return StratifyContextAndSubtypeRequest.model_validate(candidate, strict=True)
        if isinstance(candidate, Mapping):
            return StratifyContextAndSubtypeRequest.model_validate(candidate, strict=True)
        raise _InvalidM1502RequestError

    def execute(
        self, request: StratifyContextAndSubtypeRequest
    ) -> LongitudinalRecurrenceContextStratificationResult:
        return self._engine.construct(request)

    def construct(self, candidate: object) -> LongitudinalRecurrenceContextStratificationResult:
        return infer_context_and_subtype(candidate)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> LongitudinalRecurrenceContextStratificationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1502Service"]
