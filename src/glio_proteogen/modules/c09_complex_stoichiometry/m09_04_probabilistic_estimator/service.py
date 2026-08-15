"""Stateless application boundary for provisional M09-04."""

from glio_proteogen.contracts.m09_04 import (
    EstimateComplexActivityProbabilisticRequest,
    EstimateComplexActivityProbabilisticResult,
)

from .engine import M0904ProbabilisticEstimator, preflight_m0904_authorization


class M0904Service:
    """Authorize, strictly validate, and execute one M09-04 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0904ProbabilisticEstimator | None = None) -> None:
        self._engine = engine or M0904ProbabilisticEstimator()

    @staticmethod
    def validate_request(request: object) -> EstimateComplexActivityProbabilisticRequest:
        preflight_m0904_authorization(request)
        return EstimateComplexActivityProbabilisticRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: EstimateComplexActivityProbabilisticRequest,
    ) -> EstimateComplexActivityProbabilisticResult:
        return self._engine.estimate(request)

    def execute(self, request: object) -> EstimateComplexActivityProbabilisticResult:
        return self._engine.estimate(request)


__all__ = ["M0904Service"]
