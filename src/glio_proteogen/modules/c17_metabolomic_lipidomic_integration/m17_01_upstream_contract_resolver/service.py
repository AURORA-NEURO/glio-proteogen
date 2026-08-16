"""M17-01 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1701Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m17_01 import (
        ResolveVariantPeptideUpstreamContractsRequest,
        VariantPeptideUpstreamResolutionResult,
    )


class M1701Service:
    """Service wrapper with no persistence or raw artifact traversal."""

    def __init__(self) -> None:
        self._engine = M1701Engine()

    def validate_request(self, candidate: object) -> ResolveVariantPeptideUpstreamContractsRequest:
        return self._engine.validate_request(candidate)

    def resolve(self, candidate: object) -> VariantPeptideUpstreamResolutionResult:
        return self._engine.resolve(candidate)

    def replay(
        self,
        result: VariantPeptideUpstreamResolutionResult,
    ) -> VariantPeptideUpstreamResolutionResult:
        return self._engine.replay(result)


__all__ = ["M1701Service"]
