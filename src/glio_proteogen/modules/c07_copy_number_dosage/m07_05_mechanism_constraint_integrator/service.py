"""Stateless application seam for provisional M07-05."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltConstraintIntegration, M0705ConstraintEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m07_05 import (
        IntegrateProteotypeConstraintsRequest,
        IntegrateProteotypeConstraintsVerification,
    )


class M0705Service:
    """Validate, integrate, replay, and execute one constraint request."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0705ConstraintEngine()

    @staticmethod
    def validate_request(request: object) -> IntegrateProteotypeConstraintsRequest:
        return M0705ConstraintEngine.validate_request(request)

    def integrate(self, request: object) -> BuiltConstraintIntegration:
        return self._engine.integrate(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateProteotypeConstraintsVerification:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltConstraintIntegration:
        return self._engine.execute(request)


__all__ = ["M0705Service"]
