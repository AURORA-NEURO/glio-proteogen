"""Service seam for the provisional M17-06 adjudication operation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1706AdjudicationEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m17_06 import (
        AdjudicateVariantPeptideDiscrepancyQueueRequest,
        VariantPeptideAdjudicationResult,
    )


class M1706Service:
    """Typed service boundary that delegates to the stateless engine."""

    def __init__(self, engine: M1706AdjudicationEngine | None = None) -> None:
        self._engine = engine or M1706AdjudicationEngine()

    def execute(
        self, request: AdjudicateVariantPeptideDiscrepancyQueueRequest
    ) -> VariantPeptideAdjudicationResult:
        return self._engine.export(request)

    def _execute_validated(
        self, request: AdjudicateVariantPeptideDiscrepancyQueueRequest
    ) -> VariantPeptideAdjudicationResult:
        return self._engine.export(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideAdjudicationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1706Service"]
