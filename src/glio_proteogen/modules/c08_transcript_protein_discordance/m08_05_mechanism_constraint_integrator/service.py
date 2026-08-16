"""Stateless application boundary for provisional M08-05."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import (
    BuiltM0805Result,
    M0805ConstraintIntegrator,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m08_05 import (
        IntegrateTranscriptProteinConstraintsRequest,
        IntegrateTranscriptProteinConstraintsVerification,
    )


class M0805Service:
    """Validate, integrate, replay, and execute one M08-05 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0805ConstraintIntegrator | None = None) -> None:
        self._engine = engine or M0805ConstraintIntegrator()

    def validate_request(self, request: object) -> IntegrateTranscriptProteinConstraintsRequest:
        return self._engine.validate_request(request)

    def integrate(self, request: object) -> BuiltM0805Result:
        return self._engine.integrate(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateTranscriptProteinConstraintsVerification:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltM0805Result:
        return self._engine.execute(request)


__all__ = ["M0805Service"]
