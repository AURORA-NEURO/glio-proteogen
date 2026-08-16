"""Stateless service boundary for provisional M10-04."""

from glio_proteogen.contracts.m10_04 import (
    EstimateProteinRnaDiscordanceProbabilisticRequest,
    ProteinRnaDiscordanceProbabilisticResult,
)

from .engine import M1004ProbabilisticEstimatorEngine, _prepare


class M1004Service:
    """Authorize, validate, estimate, and verify one M10-04 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1004ProbabilisticEstimatorEngine | None = None) -> None:
        self._engine = engine or M1004ProbabilisticEstimatorEngine()

    @staticmethod
    def validate_request(request: object) -> EstimateProteinRnaDiscordanceProbabilisticRequest:
        return EstimateProteinRnaDiscordanceProbabilisticRequest.model_validate(
            _prepare(request), strict=True
        )

    def _execute_validated(
        self,
        request: EstimateProteinRnaDiscordanceProbabilisticRequest,
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        return self._engine.estimate(request)

    def execute(self, request: object) -> ProteinRnaDiscordanceProbabilisticResult:
        return self._engine.estimate(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1004Service"]
