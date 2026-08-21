"""Application service for M13-06."""

from glio_proteogen.contracts.m13_06 import (
    ProteotypePerturbationSensitivityResult,
    SimulateProteotypePerturbationRequest,
)
from glio_proteogen.modules.c13_proteotype.m13_06_perturbation_sensitivity.engine import (
    M1306PerturbationSensitivityEngine,
    _as_request,
)


class M1306Service:
    """Strict validation and stateless execution boundary."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1306PerturbationSensitivityEngine | None = None) -> None:
        self._engine = engine or M1306PerturbationSensitivityEngine()

    @staticmethod
    def validate_request(candidate: object) -> SimulateProteotypePerturbationRequest:
        return _as_request(candidate)

    def execute(self, request: object) -> ProteotypePerturbationSensitivityResult:
        return self._engine.compute(request)

    def verify(
        self, result: ProteotypePerturbationSensitivityResult
    ) -> ProteotypePerturbationSensitivityResult:
        return self._engine.verify(result)


__all__ = ["M1306Service"]
