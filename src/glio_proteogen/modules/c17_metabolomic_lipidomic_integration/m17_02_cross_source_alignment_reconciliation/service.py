"""Service seam for the provisional M17-02 alignment operation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1702AlignmentEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m17_02 import (
        AlignVariantPeptideCrossSourceEvidenceRequest,
        VariantPeptideCrossSourceAlignmentResult,
    )


class M1702Service:
    """Typed service boundary that delegates to the stateless engine."""

    def __init__(self, engine: M1702AlignmentEngine | None = None) -> None:
        self._engine = engine or M1702AlignmentEngine()

    def execute(
        self, request: AlignVariantPeptideCrossSourceEvidenceRequest
    ) -> VariantPeptideCrossSourceAlignmentResult:
        return self._engine.export(request)

    def _execute_validated(
        self, request: AlignVariantPeptideCrossSourceEvidenceRequest
    ) -> VariantPeptideCrossSourceAlignmentResult:
        return self._engine.export(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideCrossSourceAlignmentResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1702Service"]
