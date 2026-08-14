"""Stateless application boundary for M04-04 quality computation."""

from glio_proteogen.contracts.m04_04 import (
    ComputeProteoformQualityMetricsRequest,
    ProteoformQualityResult,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics.engine import (
    M0404ProteoformQualityEngine,
    _validate_typed_request,
)


class M0404Service:
    """Authorize and strictly validate one aggregate-only quality request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0404ProteoformQualityEngine | None = None) -> None:
        self._engine = engine or M0404ProteoformQualityEngine()

    @staticmethod
    def validate_request(request: object) -> ComputeProteoformQualityMetricsRequest:
        return _validate_typed_request(request)

    def execute(self, request: object) -> ProteoformQualityResult:
        return self._engine.compute(request)


__all__ = ["M0404Service"]
