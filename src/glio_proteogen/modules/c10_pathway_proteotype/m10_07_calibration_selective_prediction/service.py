"""Single-validation service boundary for M10-07."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltM1007Result, M1007CalibrationEngine, M1007ReplayVerification

if TYPE_CHECKING:
    from glio_proteogen.contracts.m10_07 import (
        CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    )


class M1007Service:
    __slots__ = ("_engine",)

    def __init__(self, engine: M1007CalibrationEngine | None = None) -> None:
        self._engine = engine or M1007CalibrationEngine()

    def validate_request(
        self, request: object
    ) -> CalibrateProteinRnaDiscordanceSelectivePredictionRequest:
        return self._engine.validate_request(request)

    def execute(self, request: object) -> BuiltM1007Result:
        return self._engine.execute(request)

    def verify(self, result: object, canonical: bytes | bytearray | str) -> M1007ReplayVerification:
        return self._engine.verify(result, canonical)


__all__ = ["M1007Service"]
