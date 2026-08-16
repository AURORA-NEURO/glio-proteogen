"""Stateless application boundary for provisional M08-04."""

from glio_proteogen.contracts.m08_04 import (
    EstimateTranscriptProteinProbabilisticRequest,
    EstimateTranscriptProteinProbabilisticResult,
    canonical_request_digest,
)

from .engine import (
    M0804ProbabilisticEstimator,
    preflight_m0804_authorization,
    verify_m0804_result,
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

    def verify(self, result: object) -> EstimateTranscriptProteinProbabilisticResult:
        """Verify request/result digest closure without trusting caller fields."""

        return verify_m0804_result(result)

    def replay(
        self,
        request: object,
        result: object,
    ) -> EstimateTranscriptProteinProbabilisticResult:
        """Recompute one exact request and reject any non-deterministic replay."""

        typed_request = self.validate_request(request)
        typed_result = self.verify(result)
        if typed_result.request_digest != canonical_request_digest(typed_request):
            raise ValueError("M08-04 replay request digest does not match")  # noqa: TRY003
        replayed = self._engine.estimate_validated(typed_request)
        if replayed.model_dump(mode="json") != typed_result.model_dump(mode="json"):
            raise ValueError("M08-04 replay result is not deterministic")  # noqa: TRY003
        return typed_result


__all__ = ["M0804Service"]
