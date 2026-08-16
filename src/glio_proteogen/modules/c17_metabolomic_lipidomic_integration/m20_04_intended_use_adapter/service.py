"""M20-04 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2004Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_04 import (
        AdaptProteinSubtypeIntendedUseRequest,
        ProteinSubtypeIntendedUseAdapterResult,
    )


class M2004Service:
    """Stateless service wrapper for intended-use adaptation."""

    def __init__(self) -> None:
        self._engine = M2004Engine()

    def validate_request(self, candidate: object) -> AdaptProteinSubtypeIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def adapt(self, candidate: object) -> ProteinSubtypeIntendedUseAdapterResult:
        return self._engine.adapt(candidate)

    def replay(
        self,
        result: ProteinSubtypeIntendedUseAdapterResult,
    ) -> ProteinSubtypeIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M2004Service"]
