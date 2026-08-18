"""Stateless application boundary for M05-01 protocol conformance."""

from glio_proteogen.contracts.m05_01 import (
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationProtocolConformanceResult,
)
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata.engine import (
    M0501PtmLocalizationProtocolEngine,
    _prepare_request_candidate,
    _validate_prepared_request,
)


class M0501Service:
    """Authorize and strictly validate one metadata-only protocol request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0501PtmLocalizationProtocolEngine | None = None) -> None:
        self._engine = engine or M0501PtmLocalizationProtocolEngine()

    @staticmethod
    def validate_request(request: object) -> EvaluatePtmLocalizationProtocolRequest:
        return _validate_prepared_request(_prepare_request_candidate(request))

    def _execute_validated(
        self,
        request: EvaluatePtmLocalizationProtocolRequest,
    ) -> PtmLocalizationProtocolConformanceResult:
        return self._engine._evaluate_validated(request)

    def execute(self, request: object) -> PtmLocalizationProtocolConformanceResult:
        return self._engine.evaluate(request)


__all__ = ["M0501Service"]
