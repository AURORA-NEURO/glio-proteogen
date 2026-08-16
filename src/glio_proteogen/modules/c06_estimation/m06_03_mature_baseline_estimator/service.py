"""Stateless service boundary for provisional M06-03."""

from glio_proteogen.contracts.m06_03 import (
    EstimateProteinAbundanceBaselineRequest,
    EstimateProteinAbundanceBaselineResult,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.engine import (
    M0603MatureBaselineEngine,
    _validate_typed_request,
)


class M0603Service:
    """Validate once, then execute one immutable baseline request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0603MatureBaselineEngine | None = None) -> None:
        self._engine = engine or M0603MatureBaselineEngine()

    @staticmethod
    def validate_request(request: object) -> EstimateProteinAbundanceBaselineRequest:
        return _validate_typed_request(request)

    def _execute_validated(
        self,
        request: EstimateProteinAbundanceBaselineRequest,
    ) -> EstimateProteinAbundanceBaselineResult:
        return self._engine.estimate_validated(request)

    def execute(self, request: object) -> EstimateProteinAbundanceBaselineResult:
        return self._execute_validated(self.validate_request(request))


__all__ = ["M0603Service"]
