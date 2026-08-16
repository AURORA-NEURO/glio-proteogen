"""Service seam for provisional M25-06 execution and replay verification."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_06 import (
    ChallengeProteotypeRobustnessRequest,
    ProteotypeRobustnessChallengeResult,
)

from .engine import M2506RobustnessEngine, preflight_m2506_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeProteotypeRobustnessRequest)


class M2506Service:
    """Validate, execute, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2506RobustnessEngine | None = None) -> None:
        self._engine = engine or M2506RobustnessEngine()

    def validate_request(self, request: object) -> ChallengeProteotypeRobustnessRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
            preflight_m2506_authorization(typed)
        else:
            preflight_m2506_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return typed

    def execute(self, request: object) -> ProteotypeRobustnessChallengeResult:
        return self._engine.challenge(self.validate_request(request))

    def verify_replay(
        self,
        result: ProteotypeRobustnessChallengeResult,
    ) -> ProteotypeRobustnessChallengeResult:
        return self._engine.replay(result)


__all__ = ["M2506Service"]
