"""M11-06 service boundary."""

from glio_proteogen.contracts.m11_06 import (
    SimulateVariantPeptidePerturbationsRequest,
    VariantPeptideSensitivitySimulationResult,
)

from .engine import M1106SensitivityEngine, _prepare


class M1106Service:
    """Authorize, validate, simulate, and verify one M11-06 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1106SensitivityEngine | None = None) -> None:
        self._engine = engine or M1106SensitivityEngine()

    @staticmethod
    def validate_request(request: object) -> SimulateVariantPeptidePerturbationsRequest:
        return SimulateVariantPeptidePerturbationsRequest.model_validate(
            _prepare(request), strict=True
        )

    def _execute_validated(
        self,
        request: SimulateVariantPeptidePerturbationsRequest,
    ) -> VariantPeptideSensitivitySimulationResult:
        return self._engine.register(request)

    def execute(self, request: object) -> VariantPeptideSensitivitySimulationResult:
        return self._engine.register(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideSensitivitySimulationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1106Service"]
