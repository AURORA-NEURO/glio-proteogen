"""Stateless application seam for provisional M06-05 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltConstraintIntegration, M0605MechanismConstraintEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m06_05 import (
        IntegrateProteinAbundanceConstraintsRequest,
        IntegrateProteinAbundanceConstraintsVerification,
    )


class M0605Service:
    """Validate, integrate, replay, and execute one request."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0605MechanismConstraintEngine()

    @staticmethod
    def validate_request(request: object) -> IntegrateProteinAbundanceConstraintsRequest:
        return M0605MechanismConstraintEngine.validate_request(request)

    def integrate(self, request: object) -> BuiltConstraintIntegration:
        return self._engine.integrate(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateProteinAbundanceConstraintsVerification:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltConstraintIntegration:
        return self._engine.execute(request)


__all__ = ["M0605Service"]
