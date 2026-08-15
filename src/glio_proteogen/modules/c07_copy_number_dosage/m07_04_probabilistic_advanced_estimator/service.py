"""Stateless application seam for provisional M07-04 execution and replay."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M0704ProbabilisticEstimatorEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m07_04 import (
        EstimateCopyNumberDosageProbabilisticRequest,
        EstimateCopyNumberDosageProbabilisticResult,
    )


class M0704Service:
    """Authorize, validate, execute, and verify one M07-04 request/result."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0704ProbabilisticEstimatorEngine | None = None) -> None:
        self._engine = engine or M0704ProbabilisticEstimatorEngine()

    @staticmethod
    def validate_request(request: object) -> EstimateCopyNumberDosageProbabilisticRequest:
        return M0704ProbabilisticEstimatorEngine.validate_request(request)

    def _execute_validated(
        self,
        request: EstimateCopyNumberDosageProbabilisticRequest,
    ) -> EstimateCopyNumberDosageProbabilisticResult:
        return self._engine.estimate(request)

    def execute(self, request: object) -> EstimateCopyNumberDosageProbabilisticResult:
        return self._engine.estimate(request)

    def estimate(self, request: object) -> EstimateCopyNumberDosageProbabilisticResult:
        """Alias retained for callers using the scaffold's initial spelling."""

        return self.execute(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> EstimateCopyNumberDosageProbabilisticResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M0704Service"]
