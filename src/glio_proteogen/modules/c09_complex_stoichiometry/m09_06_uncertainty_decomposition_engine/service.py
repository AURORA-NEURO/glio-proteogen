"""Single-validation service boundary for provisional M09-06."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import (
    BuiltM0906Result,
    M0906ReplayVerification,
    M0906UncertaintyDecompositionEngine,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m09_06 import DecomposeComplexActivityUncertaintyRequest


class M0906Service:
    """Validate, execute, and replay one immutable uncertainty request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0906UncertaintyDecompositionEngine | None = None) -> None:
        self._engine = engine or M0906UncertaintyDecompositionEngine()

    def validate_request(self, request: object) -> DecomposeComplexActivityUncertaintyRequest:
        return self._engine.validate_request(request)

    def execute(self, request: object) -> BuiltM0906Result:
        return self._engine.execute(request)

    def verify(
        self,
        result: object,
        canonical: bytes | bytearray | str,
    ) -> M0906ReplayVerification:
        return self._engine.verify(result, canonical)


__all__ = ["M0906Service"]
