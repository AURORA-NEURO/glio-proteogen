"""Stateless application boundary for M04-06 support harmonization."""

from glio_proteogen.contracts.m04_06 import (
    HarmonizeProteoformAnalysisRequest,
    ProteoformHarmonizationResult,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization.engine import (
    M0406ProteoformHarmonizationEngine,
    _prepare_harmonization_request_candidate,
    _validate_prepared_request,
)


class M0406Service:
    """Authorize and strictly validate one metadata-only harmonization request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0406ProteoformHarmonizationEngine | None = None,
    ) -> None:
        self._engine = engine or M0406ProteoformHarmonizationEngine()

    @staticmethod
    def validate_request(request: object) -> HarmonizeProteoformAnalysisRequest:
        return _validate_prepared_request(_prepare_harmonization_request_candidate(request))

    def _execute_validated(
        self,
        request: HarmonizeProteoformAnalysisRequest,
    ) -> ProteoformHarmonizationResult:
        return self._engine._harmonize_validated(request)

    def execute(self, request: object) -> ProteoformHarmonizationResult:
        return self._engine.harmonize(request)


__all__ = ["M0406Service"]
