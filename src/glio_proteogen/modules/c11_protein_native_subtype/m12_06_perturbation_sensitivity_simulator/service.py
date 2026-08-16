"""Application service for M12-06."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_06 import (
    BiomarkerPanelPerturbationSensitivityResult,
    SimulateBiomarkerPanelPerturbationRequest,
)
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator.engine import (  # noqa: E501
    M1206SimulatorEngine,
    preflight_m1206_authorization,
    verify_m1206_result,
)

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateBiomarkerPanelPerturbationRequest)


class M1206Service:
    """Validate, simulate, and verify one immutable request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1206SimulatorEngine | None = None) -> None:
        self._engine = engine or M1206SimulatorEngine()

    @staticmethod
    def validate_request(request: object) -> SimulateBiomarkerPanelPerturbationRequest:
        preflight_m1206_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> BiomarkerPanelPerturbationSensitivityResult:
        return self._engine.simulate(request)

    def verify(
        self, request: object, result: object
    ) -> BiomarkerPanelPerturbationSensitivityResult:
        return verify_m1206_result(request, result)


__all__ = ["M1206Service"]
