"""M19-01 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1901Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_01 import (
        ProteotypeUpstreamResolutionResult,
        ResolveProteotypeUpstreamContractsRequest,
    )


class M1901Service:
    """Service wrapper with no persistence or raw artifact traversal."""

    def __init__(self) -> None:
        self._engine = M1901Engine()

    def validate_request(
        self,
        request: object,
    ) -> ResolveProteotypeUpstreamContractsRequest:
        return self._engine.validate_request(request)

    def resolve(self, request: object) -> ProteotypeUpstreamResolutionResult:
        return self._engine.resolve(request)

    def replay(
        self,
        result: ProteotypeUpstreamResolutionResult,
    ) -> ProteotypeUpstreamResolutionResult:
        return self._engine.replay(result)


__all__ = ["M1901Service"]
