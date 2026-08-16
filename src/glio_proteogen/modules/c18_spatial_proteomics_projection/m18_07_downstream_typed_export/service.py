"""Typed service facade for M18-07."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1807Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_07 import (
        BiomarkerPanelDownstreamExportResult,
        ExportBiomarkerPanelDownstreamContractRequest,
    )


class M1807Service:
    """Stable service seam over the stateless M18-07 engine."""

    def __init__(self, engine: M1807Engine | None = None) -> None:
        self._engine = engine or M1807Engine()

    def validate_request(self, candidate: object) -> ExportBiomarkerPanelDownstreamContractRequest:
        return self._engine.validate_request(candidate)

    def execute(
        self, request: ExportBiomarkerPanelDownstreamContractRequest
    ) -> BiomarkerPanelDownstreamExportResult:
        return self._engine.export(request)

    def _execute_validated(
        self, request: ExportBiomarkerPanelDownstreamContractRequest
    ) -> BiomarkerPanelDownstreamExportResult:
        return self._engine.export(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelDownstreamExportResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1807Service"]

