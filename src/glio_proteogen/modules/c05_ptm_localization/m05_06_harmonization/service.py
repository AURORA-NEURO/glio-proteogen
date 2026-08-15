"""Stateless application boundary for provisional M05-06."""

from glio_proteogen.contracts.m05_06 import (
    HarmonizePtmLocalizationAnalysisRequest,
    PtmLocalizationHarmonizationResult,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.engine import (
    M0506PtmLocalizationHarmonizationEngine,
    _prepare,
)


class M0506Service:
    """Authorize, strictly validate, and execute one M05-06 request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0506PtmLocalizationHarmonizationEngine | None = None,
    ) -> None:
        self._engine = engine or M0506PtmLocalizationHarmonizationEngine()

    @staticmethod
    def validate_request(request: object) -> HarmonizePtmLocalizationAnalysisRequest:
        return HarmonizePtmLocalizationAnalysisRequest.model_validate(
            _prepare(request), strict=True
        )

    def _execute_validated(
        self,
        request: HarmonizePtmLocalizationAnalysisRequest,
    ) -> PtmLocalizationHarmonizationResult:
        return self._engine.harmonize(request)

    def execute(self, request: object) -> PtmLocalizationHarmonizationResult:
        return self._engine.harmonize(request)


__all__ = ["M0506Service"]
