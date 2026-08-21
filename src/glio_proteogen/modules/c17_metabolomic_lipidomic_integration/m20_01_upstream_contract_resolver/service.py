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
        request: ResolveProteinSubtypeUpstreamContractsRequest | None = None,
    ) -> ProteinSubtypeUpstreamResolutionResult:
        replayed = self._engine.replay(result)
        if request is not None and replayed.request.model_dump(mode="json") != request.model_dump(
            mode="json"
        ):
            raise ValueError("replay request mismatch")  # noqa: TRY003
        return replayed


__all__ = ["M2001Service"]
