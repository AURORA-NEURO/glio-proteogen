"""Service seam for the provisional M21-06 robustness boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_06 import (
    M2106_MAX_CANONICAL_REQUEST_BYTES,
    ChallengeComplexActivityRobustnessRequest,
    ComplexActivityRobustnessChallengeResult,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2106Engine, preflight_m2106_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeComplexActivityRobustnessRequest)


class M2106Service:
    """Validate, generate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2106Engine | None = None) -> None:
        self._engine = engine or M2106Engine()

    def validate_request(self, request: object) -> ChallengeComplexActivityRobustnessRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M2106_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2106_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(request, strict=True)
        preflight_m2106_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def generate(
        self,
        request: ChallengeComplexActivityRobustnessRequest,
    ) -> ComplexActivityRobustnessChallengeResult:
        return self._engine.generate(request)

    def replay(
        self,
        result: ComplexActivityRobustnessChallengeResult,
    ) -> ComplexActivityRobustnessChallengeResult:
        return self._engine.replay(result)


__all__ = ["M2106Service"]
