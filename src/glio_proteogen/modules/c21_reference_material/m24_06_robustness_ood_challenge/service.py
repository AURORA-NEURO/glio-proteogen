"""Strict service boundary for provisional M24-06 robustness challenges."""

from __future__ import annotations

import json
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_06 import (
    M2406_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2406RobustnessOODChallenger, preflight_m2406_authorization

_ADAPTER: Final = TypeAdapter(ChallengeBiomarkerPanelRobustnessRequest)


class M2406Service:
    __slots__ = ("_engine",)

    def __init__(self, engine: M2406RobustnessOODChallenger | None = None) -> None:
        self._engine = engine or M2406RobustnessOODChallenger()

    def validate_request(self, request: object) -> ChallengeBiomarkerPanelRobustnessRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M2406_MAX_CANONICAL_REQUEST_BYTES)
            typed = _ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2406_authorization(request)
            typed = _ADAPTER.validate_python(request, strict=True)
        preflight_m2406_authorization(typed)
        return typed

    def evaluate(self, request: object) -> BiomarkerPanelRobustnessChallengeResult:
        return self._engine.evaluate(self.validate_request(request))

    def verify_replay(
        self, result: BiomarkerPanelRobustnessChallengeResult
    ) -> BiomarkerPanelRobustnessChallengeResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: BiomarkerPanelRobustnessChallengeResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2406Service"]
