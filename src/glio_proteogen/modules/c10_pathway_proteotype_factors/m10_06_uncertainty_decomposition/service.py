"""Stateless service boundary for provisional M10-06."""

from glio_proteogen.contracts.m10_06 import (
    DecomposeProteinRnaDiscordanceUncertaintyRequest,
    ProteinRnaDiscordanceUncertaintyDecompositionResult,
)

from .engine import M1006UncertaintyDecompositionEngine, _prepare


class M1006UncertaintyDecompositionService:
    """Authorize, validate, decompose, and verify one M10-06 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1006UncertaintyDecompositionEngine | None = None) -> None:
        self._engine = engine or M1006UncertaintyDecompositionEngine()

    @staticmethod
    def validate_request(request: object) -> DecomposeProteinRnaDiscordanceUncertaintyRequest:
        return DecomposeProteinRnaDiscordanceUncertaintyRequest.model_validate(
            _prepare(request), strict=True
        )

    def _execute_validated(
        self, request: DecomposeProteinRnaDiscordanceUncertaintyRequest
    ) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        return self._engine.decompose(request)

    def execute(self, request: object) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        return self._engine.decompose(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1006UncertaintyDecompositionService"]
