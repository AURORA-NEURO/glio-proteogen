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
        request: ResolveVariantPeptideUpstreamContractsRequest | None = None,
    ) -> VariantPeptideUpstreamResolutionResult:
        replayed = self._engine.replay(result)
        if request is not None and replayed.request.model_dump(mode="json") != request.model_dump(
            mode="json"
        ):
            raise ValueError("replay request mismatch")  # noqa: TRY003
        return replayed


__all__ = ["M1701Service"]
