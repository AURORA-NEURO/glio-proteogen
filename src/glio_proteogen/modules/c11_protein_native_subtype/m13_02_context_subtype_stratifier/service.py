"""Application boundary for M13-02 context stratification."""

from glio_proteogen.contracts.m13_02 import (
    ProteotypeContextStratificationResult,
    StratifyProteotypeContextRequest,
)

from .engine import (
    M1302ContextStratifier,
    _validate_request,
)


class M1302Service:
    """Validate exactly once and execute the deterministic stratifier."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1302ContextStratifier | None = None) -> None:
        self._engine = engine or M1302ContextStratifier()

    @staticmethod
    def validate_request(request: object) -> StratifyProteotypeContextRequest:
        return _validate_request(request)

    def execute(self, request: object) -> ProteotypeContextStratificationResult:
        return self._engine.compute(request)


__all__ = ["M1302Service"]
