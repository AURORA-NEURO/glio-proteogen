"""Thin stateless service boundary for M01-04."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_04 import ComputeQualityMetricsRequest, QualityProfile
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.engine import (
    M0104MetricEngine,
)

_REQUEST_ADAPTER: Final[TypeAdapter[ComputeQualityMetricsRequest]] = TypeAdapter(
    ComputeQualityMetricsRequest
)


class M0104Service:
    """Revalidate and delegate one request to the pure metric engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0104MetricEngine | None = None) -> None:
        self._engine = engine or M0104MetricEngine()

    @staticmethod
    def validate_request(request: object) -> ComputeQualityMetricsRequest:
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> QualityProfile:
        return self._engine.compute(self.validate_request(request))


__all__ = ["M0104Service"]
