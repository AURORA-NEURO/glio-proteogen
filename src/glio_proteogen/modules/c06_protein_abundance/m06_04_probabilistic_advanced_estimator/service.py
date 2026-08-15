"""Stateless application seam for provisional M06-04 posterior estimation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M0604ProbabilisticEstimatorEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m06_04 import (
        EstimateProteinAbundanceProbabilisticRequest,
    )


class M0604Service:
    """Strictly validate one request; estimation is intentionally deferred."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0604ProbabilisticEstimatorEngine()

    @staticmethod
    def validate_request(request: object) -> EstimateProteinAbundanceProbabilisticRequest:
        return M0604ProbabilisticEstimatorEngine.validate_request(request)

    def estimate(self, request: object) -> None:
        return self._engine.estimate(request)


__all__ = ["M0604Service"]
