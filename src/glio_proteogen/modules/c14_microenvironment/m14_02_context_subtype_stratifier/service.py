"""Service seam for M14-02 validation, execution, and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_02 import (
    ProteinSubtypeContextStratificationResult,
    StratifyProteinSubtypeContextRequest,
)
from glio_proteogen.modules.c14_microenvironment.m14_02_context_subtype_stratifier.engine import (
    M1402ContextStratifier,
)


class M1402Service:
    """Typed service boundary shared by plugin, API, and CLI."""

    def __init__(self) -> None:
        self._engine = M1402ContextStratifier()
        self._request_adapter = TypeAdapter(StratifyProteinSubtypeContextRequest)

    def validate_request(self, request: object) -> StratifyProteinSubtypeContextRequest:
        return self._request_adapter.validate_python(request, strict=True)

    def _execute_validated(
        self, request: StratifyProteinSubtypeContextRequest
    ) -> ProteinSubtypeContextStratificationResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> ProteinSubtypeContextStratificationResult:
        return self._execute_validated(self.validate_request(request))

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinSubtypeContextStratificationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1402Service"]
