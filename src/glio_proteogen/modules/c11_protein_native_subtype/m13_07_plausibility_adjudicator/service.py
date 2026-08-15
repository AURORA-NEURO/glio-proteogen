"""Application boundary for M13-07 plausibility adjudication."""

from glio_proteogen.contracts.m13_07 import (
    AdjudicateProteotypePlausibilityRequest,
    ProteotypePlausibilityAdjudicationResult,
)

from .engine import (
    M1307PlausibilityEngine,
    _validate_typed_request,
)


class M1307Service:
    """Validate, execute and replay one immutable M13-07 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1307PlausibilityEngine | None = None) -> None:
        self._engine = engine or M1307PlausibilityEngine()

    @staticmethod
    def validate_request(request: object) -> AdjudicateProteotypePlausibilityRequest:
        return _validate_typed_request(request)

    def execute(self, request: object) -> ProteotypePlausibilityAdjudicationResult:
        return self._engine.adjudicate(request)

    def verify(
        self,
        request: object,
        result: object,
    ) -> ProteotypePlausibilityAdjudicationResult:
        return self._engine.verify(request, result)


__all__ = ["M1307Service"]


