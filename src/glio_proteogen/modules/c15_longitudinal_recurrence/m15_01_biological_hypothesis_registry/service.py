"""Service seam for M15-01 validation, execution, and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_01 import (
    ComplexActivityHypothesisRegistryResult,
    RegisterComplexActivityHypothesesRequest,
)

from .engine import M1501HypothesisRegistry


class M1501Service:
    """Typed service boundary shared by plugin, API, and CLI."""

    def __init__(self) -> None:
        self._engine = M1501HypothesisRegistry()
        self._request_adapter = TypeAdapter(RegisterComplexActivityHypothesesRequest)

    def validate_request(self, request: object) -> RegisterComplexActivityHypothesesRequest:
        return self._request_adapter.validate_python(request, strict=True)

    def _execute_validated(
        self, request: RegisterComplexActivityHypothesesRequest
    ) -> ComplexActivityHypothesisRegistryResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> ComplexActivityHypothesisRegistryResult:
        return self._execute_validated(self.validate_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityHypothesisRegistryResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1501Service"]
