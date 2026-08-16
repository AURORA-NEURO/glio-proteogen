"""Typed service facade for M21-08."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2108Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m21_08 import (
        AdjudicateComplexActivityEvidenceGateRequest,
        ComplexActivityEvidenceGateResult,
    )


class M2108Service:
    """Stable service seam over the stateless M21-08 engine."""

    def __init__(self, engine: M2108Engine | None = None) -> None:
        self._engine = engine or M2108Engine()

    def validate_request(self, candidate: object) -> AdjudicateComplexActivityEvidenceGateRequest:
        return self._engine.validate_request(candidate)

    def execute(
        self, request: AdjudicateComplexActivityEvidenceGateRequest
    ) -> ComplexActivityEvidenceGateResult:
        return self._engine.evaluate(request)

    def _execute_validated(
        self, request: AdjudicateComplexActivityEvidenceGateRequest
    ) -> ComplexActivityEvidenceGateResult:
        return self._engine.evaluate(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityEvidenceGateResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M2108Service"]
