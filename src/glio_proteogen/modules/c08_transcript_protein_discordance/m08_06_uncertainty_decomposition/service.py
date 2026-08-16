"""Stateless application boundary for provisional M08-06."""

from glio_proteogen.contracts.m08_06 import (
    DecomposeTranscriptProteinUncertaintyRequest,
    TranscriptProteinUncertaintyDecompositionResult,
)

from .engine import M0806UncertaintyDecompositionEngine, preflight_m0806_authorization


class M0806Service:
    """Authorize, strictly validate, execute, and verify one M08-06 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0806UncertaintyDecompositionEngine | None = None) -> None:
        self._engine = engine or M0806UncertaintyDecompositionEngine()

    @staticmethod
    def validate_request(request: object) -> DecomposeTranscriptProteinUncertaintyRequest:
        preflight_m0806_authorization(request)
        return DecomposeTranscriptProteinUncertaintyRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: DecomposeTranscriptProteinUncertaintyRequest,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        return self._engine.decompose(request)

    def execute(self, request: object) -> TranscriptProteinUncertaintyDecompositionResult:
        return self._engine.decompose(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M0806Service"]
