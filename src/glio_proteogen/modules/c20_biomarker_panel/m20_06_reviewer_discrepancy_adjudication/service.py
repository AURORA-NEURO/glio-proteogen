"""M20-06 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2006Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_06 import (
        AdjudicateProteinSubtypeQueueRequest,
        ProteinSubtypeAdjudicationResult,
    )


class M2006Service:
    """Stateless service wrapper for adjudication and exact replay."""

    def __init__(self) -> None:
        self._engine = M2006Engine()

    def validate_request(self, candidate: object) -> AdjudicateProteinSubtypeQueueRequest:
        return self._engine.validate_request(candidate)

    def adjudicate(self, candidate: object) -> ProteinSubtypeAdjudicationResult:
        return self._engine.adjudicate(candidate)

    def replay(self, result: ProteinSubtypeAdjudicationResult) -> ProteinSubtypeAdjudicationResult:
        return self._engine.replay(result)


__all__ = ["M2006Service"]
