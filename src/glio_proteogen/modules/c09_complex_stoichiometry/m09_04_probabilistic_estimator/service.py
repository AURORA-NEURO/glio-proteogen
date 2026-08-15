"""Stateless application boundary for provisional M09-04."""

from glio_proteogen.contracts.m09_04 import (
    EstimateComplexActivityProbabilisticRequest,
    EstimateComplexActivityProbabilisticResult,
    EstimateComplexActivityProbabilisticVerification,
)

from .engine import (
    BuiltM0904Result,
    M0904ProbabilisticEstimator,
    preflight_m0904_authorization,
)


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

    def build(self, request: object) -> BuiltM0904Result:
        """Return a typed result and its canonical bytes for API/CLI delivery."""

        return self._engine.build(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> EstimateComplexActivityProbabilisticVerification:
        """Verify both canonical content and the result replay digest."""

        return self._engine.verify(result, canonical_bytes)


__all__ = ["M0904Service"]
