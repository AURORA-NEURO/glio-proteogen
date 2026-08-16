"""M12-05 service seam for validation, execution, and replay verification."""

from glio_proteogen.contracts.m12_05 import (
    BiomarkerPanelLongitudinalEvolutionResult,
    ModelBiomarkerPanelLongitudinalEvolutionRequest,
)

from .engine import M1205LongitudinalEngine, preflight_longitudinal_authorization


class M1205Service:
    """Authorize, strictly validate, infer, and verify one M12-05 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1205LongitudinalEngine | None = None) -> None:
        self._engine = engine or M1205LongitudinalEngine()

    @staticmethod
    def validate_request(request: object) -> ModelBiomarkerPanelLongitudinalEvolutionRequest:
        preflight_longitudinal_authorization(request)
        return ModelBiomarkerPanelLongitudinalEvolutionRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: ModelBiomarkerPanelLongitudinalEvolutionRequest,
    ) -> BiomarkerPanelLongitudinalEvolutionResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> BiomarkerPanelLongitudinalEvolutionResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelLongitudinalEvolutionResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1205Service"]
