"""Typed service facade for M22-06."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2206Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m22_06 import (
        ChallengeProteinRnaDiscordanceRobustnessRequest,
        ProteinRnaDiscordanceRobustnessChallengeResult,
    )


class M2206Service:
    """Stable service seam over the stateless M22-06 engine."""

    def __init__(self, engine: M2206Engine | None = None) -> None:
        self._engine = engine or M2206Engine()

    def validate_request(
        self, candidate: object
    ) -> ChallengeProteinRnaDiscordanceRobustnessRequest:
        return self._engine.validate_request(candidate)

    def execute(
        self, request: ChallengeProteinRnaDiscordanceRobustnessRequest
    ) -> ProteinRnaDiscordanceRobustnessChallengeResult:
        return self._engine.evaluate(request)

    def _execute_validated(
        self, request: ChallengeProteinRnaDiscordanceRobustnessRequest
    ) -> ProteinRnaDiscordanceRobustnessChallengeResult:
        return self._engine.evaluate(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceRobustnessChallengeResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M2206Service"]
