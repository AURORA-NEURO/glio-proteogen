"""Service seam for the provisional M14-06 runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_06 import SimulateProteinSubtypePerturbationsRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1406SensitivityEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m14_06 import ProteinSubtypeSensitivitySimulationResult

_REQUEST_ADAPTER = TypeAdapter(SimulateProteinSubtypePerturbationsRequest)


class M1406Service:
    """Keep adapter execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1406SensitivityEngine | None = None) -> None:
        self._engine = engine or M1406SensitivityEngine()

    def execute(
        self, request: SimulateProteinSubtypePerturbationsRequest
    ) -> ProteinSubtypeSensitivitySimulationResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> SimulateProteinSubtypePerturbationsRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: SimulateProteinSubtypePerturbationsRequest
    ) -> ProteinSubtypeSensitivitySimulationResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeSensitivitySimulationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1406Service"]
