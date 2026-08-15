"""Stateless application seam for provisional M07-04 posterior estimation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M0704ProbabilisticEstimatorEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m07_04 import EstimateCopyNumberDosageProbabilisticRequest


class M0704Service:
    """Strictly validate one request; estimation is intentionally deferred."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0704ProbabilisticEstimatorEngine()

    @staticmethod
    def validate_request(request: object) -> EstimateCopyNumberDosageProbabilisticRequest:
        return M0704ProbabilisticEstimatorEngine.validate_request(request)

    def estimate(self, request: object) -> None:
        return self._engine.estimate(request)


__all__ = ["M0704Service"]
