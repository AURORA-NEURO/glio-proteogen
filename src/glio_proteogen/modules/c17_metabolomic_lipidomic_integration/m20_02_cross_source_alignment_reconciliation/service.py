"""M20-02 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2002Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_02 import (
        AlignProteinSubtypeSourcesRequest,
        ProteinSubtypeAlignmentResult,
    )


class M2002Service:
    """Stateless service wrapper with no raw artifact traversal."""

    def __init__(self) -> None:
        self._engine = M2002Engine()

    def validate_request(self, candidate: object) -> AlignProteinSubtypeSourcesRequest:
        return self._engine.validate_request(candidate)

    def reconcile(self, candidate: object) -> ProteinSubtypeAlignmentResult:
        return self._engine.resolve(candidate)

    def verify(self, result: ProteinSubtypeAlignmentResult) -> ProteinSubtypeAlignmentResult:
        return self._engine.replay(result)


__all__ = ["M2002Service"]
