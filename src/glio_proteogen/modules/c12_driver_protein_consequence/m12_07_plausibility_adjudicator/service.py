"""Application service seam for M12-07."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_07 import (
    AdjudicateBiomarkerPanelPlausibilityRequest,
    BiomarkerPanelPlausibilityAdjudicationResult,
)

from .engine import (
    M1207PlausibilityAdjudicatorEngine,
    preflight_m1207_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateBiomarkerPanelPlausibilityRequest)


class M1207Service:
    """Validate, execute and replay-verify one immutable M12-07 request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M1207PlausibilityAdjudicatorEngine | None = None,
    ) -> None:
        self._engine = engine or M1207PlausibilityAdjudicatorEngine()

    @staticmethod
    def validate_request(
        request: object,
    ) -> AdjudicateBiomarkerPanelPlausibilityRequest:
        preflight_m1207_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> BiomarkerPanelPlausibilityAdjudicationResult:
        return self._engine.adjudicate(request)

    def verify(
        self,
        request: object,
        result: object,
    ) -> BiomarkerPanelPlausibilityAdjudicationResult:
        return self._engine.verify(request, result)


__all__ = ["M1207Service"]
