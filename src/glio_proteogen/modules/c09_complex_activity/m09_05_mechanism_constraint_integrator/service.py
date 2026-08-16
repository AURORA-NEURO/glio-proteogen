"""Stateless application boundary for provisional M09-05."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltM0905Result, M0905ConstraintIntegrator

if TYPE_CHECKING:
    from glio_proteogen.contracts.m09_05 import (
        IntegrateComplexActivityConstraintsRequest,
        IntegrateComplexActivityConstraintsVerification,
    )


class M0905Service:
    """Validate, integrate, replay, and execute one M09-05 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0905ConstraintIntegrator | None = None) -> None:
        self._engine = engine or M0905ConstraintIntegrator()

    def validate_request(self, request: object) -> IntegrateComplexActivityConstraintsRequest:
        return self._engine.validate_request(request)

    def integrate(self, request: object) -> BuiltM0905Result:
        return self._engine.integrate(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateComplexActivityConstraintsVerification:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltM0905Result:
        return self._engine.execute(request)


__all__ = ["M0905Service"]
