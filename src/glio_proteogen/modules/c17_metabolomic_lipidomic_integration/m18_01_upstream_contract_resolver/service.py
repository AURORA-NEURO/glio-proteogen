"""M18-01 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1801Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_01 import (
        BiomarkerPanelUpstreamResolutionResult,
        ResolveBiomarkerPanelUpstreamContractsRequest,
    )


class M1801Service:
    """Service wrapper with no persistence or raw artifact traversal."""

    def __init__(self) -> None:
        self._engine = M1801Engine()

    def validate_request(self, candidate: object) -> ResolveBiomarkerPanelUpstreamContractsRequest:
        return self._engine.validate_request(candidate)

    def resolve(self, candidate: object) -> BiomarkerPanelUpstreamResolutionResult:
        return self._engine.resolve(candidate)

    def replay(
        self,
        result: BiomarkerPanelUpstreamResolutionResult,
    ) -> BiomarkerPanelUpstreamResolutionResult:
        return self._engine.replay(result)


__all__ = ["M1801Service"]
