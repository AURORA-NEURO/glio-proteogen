"""M11-05 service boundary."""

from glio_proteogen.contracts.m11_05 import (
    ModelVariantPeptideLongitudinalEvolutionRequest,
    VariantPeptideLongitudinalEvolutionResult,
)

from .engine import M1105LongitudinalEngine, _prepare


class M1105Service:
    """Authorize, validate, execute, and verify one M11-05 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1105LongitudinalEngine | None = None) -> None:
        self._engine = engine or M1105LongitudinalEngine()

    @staticmethod
    def validate_request(request: object) -> ModelVariantPeptideLongitudinalEvolutionRequest:
        return ModelVariantPeptideLongitudinalEvolutionRequest.model_validate(
            _prepare(request), strict=True
        )

    def _execute_validated(
        self,
        request: ModelVariantPeptideLongitudinalEvolutionRequest,
    ) -> VariantPeptideLongitudinalEvolutionResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> VariantPeptideLongitudinalEvolutionResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideLongitudinalEvolutionResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1105Service"]
