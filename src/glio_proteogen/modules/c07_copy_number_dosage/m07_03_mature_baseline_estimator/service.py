"""Stateless application boundary for provisional M07-03."""

from glio_proteogen.contracts.m07_03 import (
    EstimateCopyNumberDosageBaselineRequest,
    EstimateCopyNumberDosageBaselineResult,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_03_mature_baseline_estimator.engine import (
    M0703MatureBaselineEngine,
    preflight_m0703_authorization,
)


class M0703Service:
    """Authorize, strictly validate, and execute one M07-03 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0703MatureBaselineEngine | None = None) -> None:
        self._engine = engine or M0703MatureBaselineEngine()

    @staticmethod
    def validate_request(request: object) -> EstimateCopyNumberDosageBaselineRequest:
        preflight_m0703_authorization(request)
        return EstimateCopyNumberDosageBaselineRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: EstimateCopyNumberDosageBaselineRequest,
    ) -> EstimateCopyNumberDosageBaselineResult:
        return self._engine.estimate(request)

    def execute(self, request: object) -> EstimateCopyNumberDosageBaselineResult:
        return self._engine.estimate(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> EstimateCopyNumberDosageBaselineResult:
        """Verify a result receipt and optionally replay the request."""

        return self._engine.verify(result, replay=replay)


__all__ = ["M0703Service"]
