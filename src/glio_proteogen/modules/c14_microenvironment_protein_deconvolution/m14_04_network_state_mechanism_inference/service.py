"""Service seam for the provisional M14-04 runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_04 import InferProteinSubtypeMechanismRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from glio_proteogen.contracts.m14_04 import ProteinSubtypeMechanismInferenceResult

from .engine import M1404MechanismEngine

_REQUEST_ADAPTER = TypeAdapter(InferProteinSubtypeMechanismRequest)


class M1404Service:
    """Keep adapter execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1404MechanismEngine | None = None) -> None:
        self._engine = engine or M1404MechanismEngine()

    def execute(
        self, request: InferProteinSubtypeMechanismRequest
    ) -> ProteinSubtypeMechanismInferenceResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> InferProteinSubtypeMechanismRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: InferProteinSubtypeMechanismRequest
    ) -> ProteinSubtypeMechanismInferenceResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanismInferenceResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1404Service"]


