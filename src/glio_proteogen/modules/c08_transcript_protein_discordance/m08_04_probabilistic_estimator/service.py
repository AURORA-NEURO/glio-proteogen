"""Stateless application boundary for provisional M08-04."""

from glio_proteogen.contracts.m08_04 import (
    EstimateTranscriptProteinProbabilisticRequest,
    EstimateTranscriptProteinProbabilisticResult,
)

from .engine import (
    M0804ProbabilisticEstimator,
    preflight_m0804_authorization,
)


class M0804Service:
    """Authorize, strictly validate, and execute one M08-04 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0804ProbabilisticEstimator | None = None) -> None:
        self._engine = engine or M0804ProbabilisticEstimator()

    @staticmethod
    def validate_request(request: object) -> EstimateTranscriptProteinProbabilisticRequest:
        preflight_m0804_authorization(request)
        return EstimateTranscriptProteinProbabilisticRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: EstimateTranscriptProteinProbabilisticRequest,
    ) -> EstimateTranscriptProteinProbabilisticResult:
        return self._engine.estimate(request)

    def execute(self, request: object) -> EstimateTranscriptProteinProbabilisticResult:
        return self._engine.estimate(request)


__all__ = ["M0804Service"]
