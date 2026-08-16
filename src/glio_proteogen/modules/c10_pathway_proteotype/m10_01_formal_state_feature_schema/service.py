"""Stateless application boundary for M10-01."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltM1001Result, M1001FormalStateEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m10_01 import (
        ValidateProteinRnaDiscordanceStateRequest,
        ValidateProteinRnaDiscordanceStateVerification,
    )


class M1001Service:
    """Validate, execute, and replay one M10-01 request without persistence."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1001FormalStateEngine | None = None) -> None:
        self._engine = engine or M1001FormalStateEngine()

    def validate_request(self, request: object) -> ValidateProteinRnaDiscordanceStateRequest:
        return self._engine.validate_request(request)

    def execute(self, request: object) -> BuiltM1001Result:
        return self._engine.execute(request)

    def validate(self, request: object) -> ValidateProteinRnaDiscordanceStateRequest:
        return self._engine.validate(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ValidateProteinRnaDiscordanceStateVerification:
        return self._engine.verify(result, canonical_bytes)

    def integrate(self, request: object) -> BuiltM1001Result:
        return self._engine.integrate(request)


__all__ = ["M1001Service"]
