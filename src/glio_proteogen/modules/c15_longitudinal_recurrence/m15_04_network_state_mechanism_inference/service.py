"""Service seam for M15-04 validation, execution, and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_04 import (
    ComplexActivityMechanismInferenceResult,
    InferComplexActivityMechanismRequest,
)

from .engine import M1504MechanismInference


class M1504Service:
    """Typed service boundary shared by plugin, API, and CLI."""

    def __init__(self) -> None:
        self._engine = M1504MechanismInference()
        self._request_adapter = TypeAdapter(InferComplexActivityMechanismRequest)

    def validate_request(self, request: object) -> InferComplexActivityMechanismRequest:
        return self._request_adapter.validate_python(request, strict=True)

    def _execute_validated(
        self, request: InferComplexActivityMechanismRequest
    ) -> ComplexActivityMechanismInferenceResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> ComplexActivityMechanismInferenceResult:
        return self._execute_validated(self.validate_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanismInferenceResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1504Service"]
