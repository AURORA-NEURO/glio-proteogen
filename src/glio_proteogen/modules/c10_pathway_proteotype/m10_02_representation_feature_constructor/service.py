"""Stateless service seam for M10-02."""

from glio_proteogen.contracts.m10_02 import (
    ConstructProteinRnaRepresentationRequest,
    ProteinRnaRepresentationResult,
)

from .engine import (
    M1002RepresentationEngine,
    _validate_request,
)


class M1002Service:
    """Keep validation and execution separate for API, CLI, and plugin parity."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1002RepresentationEngine | None = None) -> None:
        self._engine = engine or M1002RepresentationEngine()

    @staticmethod
    def validate_request(request: object) -> ConstructProteinRnaRepresentationRequest:
        return _validate_request(request)

    def execute(self, request: object) -> ProteinRnaRepresentationResult:
        return self._engine.compute(request)


__all__ = ["M1002Service"]
