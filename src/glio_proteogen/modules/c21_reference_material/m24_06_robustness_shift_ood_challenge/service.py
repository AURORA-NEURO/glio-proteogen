"""Service seam for strict M24-06 challenge and replay operations."""

from __future__ import annotations

import json
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_06 import (
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
)

from .engine import M2406RobustnessEngine, preflight_m2406_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeBiomarkerPanelRobustnessRequest)


class M2406Service:
    """Typed service boundary sharing one canonical challenge engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2406RobustnessEngine | None = None) -> None:
        self._engine = engine or M2406RobustnessEngine()

    def validate_request(self, request: object) -> ChallengeBiomarkerPanelRobustnessRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2406_authorization(typed)
        return typed

    def challenge(self, request: object) -> BiomarkerPanelRobustnessChallengeResult:
        return self._engine.challenge(self.validate_request(request))

    def verify_replay(
        self, result: BiomarkerPanelRobustnessChallengeResult
    ) -> BiomarkerPanelRobustnessChallengeResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: BiomarkerPanelRobustnessChallengeResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2406Service"]
