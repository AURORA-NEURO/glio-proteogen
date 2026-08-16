"""Service seam for M14-07 validation, execution, and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_07 import (
    AdjudicateProteinSubtypePlausibilityRequest,
    ProteinSubtypePlausibilityAdjudicationResult,
)

from .engine import (
    M1407PlausibilityAdjudicator,
)


class M1407Service:
    """Typed service boundary shared by plugin, API, and CLI."""

    def __init__(self) -> None:
        self._engine = M1407PlausibilityAdjudicator()
        self._request_adapter = TypeAdapter(AdjudicateProteinSubtypePlausibilityRequest)

    def validate_request(self, request: object) -> AdjudicateProteinSubtypePlausibilityRequest:
        return self._request_adapter.validate_python(request, strict=True)

    def _execute_validated(
        self, request: AdjudicateProteinSubtypePlausibilityRequest
    ) -> ProteinSubtypePlausibilityAdjudicationResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> ProteinSubtypePlausibilityAdjudicationResult:
        return self._execute_validated(self.validate_request(request))

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinSubtypePlausibilityAdjudicationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1407Service"]
