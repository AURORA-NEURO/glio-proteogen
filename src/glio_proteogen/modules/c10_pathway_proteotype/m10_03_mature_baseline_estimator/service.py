"""Stateless M10-03 service seam."""

from glio_proteogen.contracts.m10_03 import (
    EstimateProteinRnaDiscordanceBaselineRequest,
    ProteinRnaDiscordanceBaselineResult,
)

from .engine import M1003BaselineEngine, _validate_request


class M1003Service:
    __slots__ = ("_engine",)

    def __init__(self, engine: M1003BaselineEngine | None = None) -> None:
        self._engine = engine or M1003BaselineEngine()

    @staticmethod
    def validate_request(request: object) -> EstimateProteinRnaDiscordanceBaselineRequest:
        return _validate_request(request)

    def execute(self, request: object) -> ProteinRnaDiscordanceBaselineResult:
        return self._engine.compute(request)


__all__ = ["M1003Service"]
