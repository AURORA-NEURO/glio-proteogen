"""Stateless application boundary for M05-04 quality computation."""

from glio_proteogen.contracts.m05_04 import (
    ComputePtmLocalizationQualityMetricsRequest,
    PtmLocalizationQualityResult,
)
from glio_proteogen.contracts.m05_04.v1 import _ValidatedRequestCapability
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics.engine import (
    M0504PtmLocalizationQualityEngine,
    _compute_result,
    _validate_typed_request,
    _validated_request_capability,
)


class M0504Service:
    """Authorize and strictly validate one aggregate-only quality request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0504PtmLocalizationQualityEngine | None = None) -> None:
        self._engine = engine or M0504PtmLocalizationQualityEngine()

    @staticmethod
    def validate_request(request: object) -> ComputePtmLocalizationQualityMetricsRequest:
        return _validate_typed_request(request)

    def execute(self, request: object) -> PtmLocalizationQualityResult:
        return self._engine.compute(request)

    @staticmethod
    def _admit_request(request: object) -> _ValidatedRequestCapability:
        """Issue one private immutable admission proof for validate-then-run adapters."""

        return _validated_request_capability(request)

    @staticmethod
    def _execute_validated(
        capability: _ValidatedRequestCapability,
    ) -> PtmLocalizationQualityResult:
        """Consume an exact sealed admission without repeating upstream replay."""

        return _compute_result(capability)


__all__ = ["M0504Service"]
