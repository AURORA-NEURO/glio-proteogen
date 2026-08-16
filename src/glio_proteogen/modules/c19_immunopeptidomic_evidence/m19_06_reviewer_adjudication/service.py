"""M19-06 stateless service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1906Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_06 import (
        AdjudicateProteotypeQueueRequest,
        ProteotypeAdjudicationResult,
    )


class M1906Service:
    """Service wrapper exposing validation, adjudication, and exact replay."""

    def __init__(self) -> None:
        self._engine = M1906Engine()

    def validate_request(self, candidate: object) -> AdjudicateProteotypeQueueRequest:
        return self._engine.validate_request(candidate)

    def adjudicate(self, candidate: object) -> ProteotypeAdjudicationResult:
        return self._engine.adapt(candidate)

    def replay(self, result: ProteotypeAdjudicationResult) -> ProteotypeAdjudicationResult:
        return self._engine.replay(result)


__all__ = ["M1906Service"]
