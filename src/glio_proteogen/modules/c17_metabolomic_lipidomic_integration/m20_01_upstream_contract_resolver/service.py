"""M20-01 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2001Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_01 import (
        ProteinSubtypeUpstreamResolutionResult,
        ResolveProteinSubtypeUpstreamContractsRequest,
    )


class M2001Service:
    """Service wrapper with no persistence or raw artifact traversal."""

    def __init__(self) -> None:
        self._engine = M2001Engine()

    def validate_request(self, candidate: object) -> ResolveProteinSubtypeUpstreamContractsRequest:
        return self._engine.validate_request(candidate)

    def resolve(self, candidate: object) -> ProteinSubtypeUpstreamResolutionResult:
        return self._engine.resolve(candidate)

    def replay(
        self,
        result: ProteinSubtypeUpstreamResolutionResult,
    ) -> ProteinSubtypeUpstreamResolutionResult:
        return self._engine.replay(result)


__all__ = ["M2001Service"]
