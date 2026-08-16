"""Typed service facade for M19-04 intended-use adaptation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1904Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_04 import (
        AdaptProteotypeIntendedUseRequest,
        ProteotypeIntendedUseAdapterResult,
    )


class M1904Service:
    """Keep validation, adaptation and replay on one deterministic seam."""

    def __init__(self) -> None:
        self._engine = M1904Engine()

    def validate_request(self, candidate: object) -> AdaptProteotypeIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def adapt(self, candidate: object) -> ProteotypeIntendedUseAdapterResult:
        return self._engine.adapt(candidate)

    def replay(
        self,
        result: ProteotypeIntendedUseAdapterResult,
    ) -> ProteotypeIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M1904Service"]
