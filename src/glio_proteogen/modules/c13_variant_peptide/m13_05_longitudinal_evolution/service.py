"""M13-05 service seam for validation, execution, and replay verification."""

from glio_proteogen.contracts.m13_05 import (
    ModelProteotypeLongitudinalEvolutionRequest,
    ProteotypeLongitudinalEvolutionResult,
)

from .engine import M1305LongitudinalEngine, preflight_longitudinal_authorization


class M1305Service:
    """Authorize, strictly validate, infer, and verify one M13-05 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1305LongitudinalEngine | None = None) -> None:
        self._engine = engine or M1305LongitudinalEngine()

    @staticmethod
    def validate_request(request: object) -> ModelProteotypeLongitudinalEvolutionRequest:
        preflight_longitudinal_authorization(request)
        return ModelProteotypeLongitudinalEvolutionRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: ModelProteotypeLongitudinalEvolutionRequest,
    ) -> ProteotypeLongitudinalEvolutionResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> ProteotypeLongitudinalEvolutionResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeLongitudinalEvolutionResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1305Service"]
