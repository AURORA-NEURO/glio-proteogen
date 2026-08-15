"""Service seam for the provisional M11-04 runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_04 import InferVariantPeptideMechanismRequest

if TYPE_CHECKING:
    from glio_proteogen.contracts.m11_04 import VariantPeptideMechanismInferenceResult

from .engine import M1104MechanismEngine

_REQUEST_ADAPTER = TypeAdapter(InferVariantPeptideMechanismRequest)


class M1104Service:
    """Keep adapter execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1104MechanismEngine | None = None) -> None:
        self._engine = engine or M1104MechanismEngine()

    def execute(
        self, request: InferVariantPeptideMechanismRequest
    ) -> VariantPeptideMechanismInferenceResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> InferVariantPeptideMechanismRequest:
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def _execute_validated(
        self, request: InferVariantPeptideMechanismRequest
    ) -> VariantPeptideMechanismInferenceResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideMechanismInferenceResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1104Service"]
