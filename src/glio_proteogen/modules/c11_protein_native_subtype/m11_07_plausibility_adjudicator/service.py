"""Application boundary for M11-07 plausibility adjudication."""

from glio_proteogen.contracts.m11_07 import (
    AdjudicateVariantPeptidePlausibilityRequest,
    VariantPeptidePlausibilityAdjudicationResult,
)

from .engine import (
    M1107PlausibilityEngine,
    _validate_typed_request,
)


class M1107Service:
    """Validate, execute and replay one immutable M11-07 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1107PlausibilityEngine | None = None) -> None:
        self._engine = engine or M1107PlausibilityEngine()

    @staticmethod
    def validate_request(request: object) -> AdjudicateVariantPeptidePlausibilityRequest:
        return _validate_typed_request(request)

    def execute(self, request: object) -> VariantPeptidePlausibilityAdjudicationResult:
        return self._engine.adjudicate(request)

    def verify(
        self,
        request: object,
        result: object,
    ) -> VariantPeptidePlausibilityAdjudicationResult:
        return self._engine.verify(request, result)


__all__ = ["M1107Service"]
