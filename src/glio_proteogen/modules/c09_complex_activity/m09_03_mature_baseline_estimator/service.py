"""Stateless service boundary for the M09-03 baseline estimator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltM0903Result, M0903BaselineEstimator

if TYPE_CHECKING:
    from glio_proteogen.contracts.m09_03 import EstimateComplexActivityBaselineRequest


class M0903Service:
    """Validate, estimate, replay, and execute one request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0903BaselineEstimator | None = None) -> None:
        self._engine = engine or M0903BaselineEstimator()

    def validate_request(self, request: object) -> EstimateComplexActivityBaselineRequest:
        return self._engine.validate_request(request)

    def construct(self, request: object) -> BuiltM0903Result:
        return self._engine.construct(request)

    def verify(self, result: object, canonical_bytes: bytes | None = None) -> bool:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltM0903Result:
        return self._engine.execute(request)


__all__ = ["M0903Service"]
