"""Service seam for provisional M15-06 sensitivity simulation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_06 import SimulateComplexActivityPerturbationsRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1506SensitivitySimulatorEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m15_06 import ComplexActivitySensitivitySimulationResult

_REQUEST_ADAPTER = TypeAdapter(SimulateComplexActivityPerturbationsRequest)


class M1506Service:
    """Keep adapter execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1506SensitivitySimulatorEngine | None = None) -> None:
        self._engine = engine or M1506SensitivitySimulatorEngine()

    def execute(
        self, request: SimulateComplexActivityPerturbationsRequest
    ) -> ComplexActivitySensitivitySimulationResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> SimulateComplexActivityPerturbationsRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: SimulateComplexActivityPerturbationsRequest
    ) -> ComplexActivitySensitivitySimulationResult:
        return self._engine.infer(request)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ComplexActivitySensitivitySimulationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1506Service"]
