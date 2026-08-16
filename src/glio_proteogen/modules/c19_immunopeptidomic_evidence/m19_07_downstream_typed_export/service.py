"""Typed service facade for M19-07."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1907Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_07 import (
        ExportProteotypeDownstreamContractRequest,
        ProteotypeDownstreamExportResult,
    )


class M1907Service:
    """Stable service seam over the stateless M19-07 engine."""

    def __init__(self, engine: M1907Engine | None = None) -> None:
        self._engine = engine or M1907Engine()

    def validate_request(self, candidate: object) -> ExportProteotypeDownstreamContractRequest:
        return self._engine.validate_request(candidate)

    def execute(self, candidate: object) -> ProteotypeDownstreamExportResult:
        return self._engine.export(candidate)

    def _execute_validated(
        self, request: ExportProteotypeDownstreamContractRequest
    ) -> ProteotypeDownstreamExportResult:
        return self._engine.export(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeDownstreamExportResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1907Service"]
