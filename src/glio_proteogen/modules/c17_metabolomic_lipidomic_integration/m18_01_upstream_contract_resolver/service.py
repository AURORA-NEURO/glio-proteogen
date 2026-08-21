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
        request: ResolveBiomarkerPanelUpstreamContractsRequest | None = None,
    ) -> BiomarkerPanelUpstreamResolutionResult:
        replayed = self._engine.replay(result)
        if request is not None and replayed.request.model_dump(mode="json") != request.model_dump(
            mode="json"
        ):
            raise ValueError("replay request mismatch")  # noqa: TRY003
        return replayed


__all__ = ["M1801Service"]
