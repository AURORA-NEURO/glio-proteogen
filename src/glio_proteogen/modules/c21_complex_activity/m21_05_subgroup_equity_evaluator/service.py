"""Typed service facade for M21-05."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2105Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m21_05 import (
        ComplexActivitySubgroupEvaluationResult,
        EvaluateComplexActivitySubgroupEquityRequest,
    )


class M2105Service:
    """Stable service seam over the stateless M21-05 engine."""

    def __init__(self, engine: M2105Engine | None = None) -> None:
        self._engine = engine or M2105Engine()

    def validate_request(self, candidate: object) -> EvaluateComplexActivitySubgroupEquityRequest:
        return self._engine.validate_request(candidate)

    def execute(
        self, request: EvaluateComplexActivitySubgroupEquityRequest
    ) -> ComplexActivitySubgroupEvaluationResult:
        return self._engine.evaluate(request)

    def _execute_validated(
        self, request: EvaluateComplexActivitySubgroupEquityRequest
    ) -> ComplexActivitySubgroupEvaluationResult:
        return self._engine.evaluate(request)

    def verify(
        self,
        result: object,
        *,
        request: EvaluateComplexActivitySubgroupEquityRequest | None = None,
        replay: bool = True,
    ) -> ComplexActivitySubgroupEvaluationResult:
        if request is not None:
            parsed = self._engine.verify(result, replay=False)
            if parsed.request.model_dump(mode="json") != request.model_dump(mode="json"):
                raise ValueError
        return self._engine.verify(result, replay=replay)


__all__ = ["M2105Service"]
