"""Typed service facade for M20-07."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2007Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_07 import (
        ExportProteinSubtypeDownstreamContractRequest,
        ProteinSubtypeDownstreamExportResult,
    )


class M2007Service:
    """Stable service seam over the stateless M20-07 engine."""

    def __init__(self, engine: M2007Engine | None = None) -> None:
        self._engine = engine or M2007Engine()

    def validate_request(self, candidate: object) -> ExportProteinSubtypeDownstreamContractRequest:
        return self._engine.validate_request(candidate)

    def execute(
        self, request: ExportProteinSubtypeDownstreamContractRequest
    ) -> ProteinSubtypeDownstreamExportResult:
        return self._engine.export(request)

    def _execute_validated(
        self, request: ExportProteinSubtypeDownstreamContractRequest
    ) -> ProteinSubtypeDownstreamExportResult:
        return self._engine.export(request)

    def verify(
        self,
        result: object,
        *,
        request: ExportProteinSubtypeDownstreamContractRequest | None = None,
        replay: bool = True,
    ) -> ProteinSubtypeDownstreamExportResult:
        if request is not None:
            parsed = self._engine.verify(result, replay=False)
            if parsed.request.model_dump(mode="json") != request.model_dump(mode="json"):
                raise ValueError
        return self._engine.verify(result, replay=replay)


__all__ = ["M2007Service"]
