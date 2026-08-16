"""M19-02 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1902Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_02 import (
        AlignProteotypeSourcesRequest,
        ProteotypeAlignmentResult,
    )


class M1902Service:
    """Service wrapper with no persistence or raw artifact traversal."""

    def __init__(self) -> None:
        self._engine = M1902Engine()

    def validate_request(self, request: object) -> AlignProteotypeSourcesRequest:
        return self._engine.validate_request(request)

    def align(self, request: object) -> ProteotypeAlignmentResult:
        return self._engine.align(request)

    def replay(self, result: ProteotypeAlignmentResult) -> ProteotypeAlignmentResult:
        return self._engine.replay(result)


__all__ = ["M1902Service"]
