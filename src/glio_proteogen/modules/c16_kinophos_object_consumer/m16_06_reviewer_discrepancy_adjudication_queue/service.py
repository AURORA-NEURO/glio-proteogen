"""Service wrapper for M16-06 queue adjudication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1606Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m16_06 import (
        AdjudicateProteinRnaDiscordanceQueueRequest,
        ProteinRnaDiscordanceAdjudicationResult,
    )


class M1606Service:
    """Typed service facade with no persistence or model execution."""

    def __init__(self) -> None:
        self._engine = M1606Engine()

    def validate_request(self, candidate: object) -> AdjudicateProteinRnaDiscordanceQueueRequest:
        return self._engine.validate_request(candidate)

    def adjudicate(self, candidate: object) -> ProteinRnaDiscordanceAdjudicationResult:
        return self._engine.adjudicate(candidate)

    def replay(
        self, result: ProteinRnaDiscordanceAdjudicationResult
    ) -> ProteinRnaDiscordanceAdjudicationResult:
        return self._engine.replay(result)


__all__ = ["M1606Service"]
