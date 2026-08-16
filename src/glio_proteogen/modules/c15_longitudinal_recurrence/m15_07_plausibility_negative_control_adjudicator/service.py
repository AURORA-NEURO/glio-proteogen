"""Service seam for M15-07 validation, execution, and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_07 import (
    AdjudicateComplexActivityPlausibilityRequest,
    ComplexActivityPlausibilityAdjudicationResult,
)

from .engine import M1507PlausibilityAdjudicator


class M1507Service:
    """Typed service boundary shared by plugin, API, and CLI."""

    def __init__(self) -> None:
        self._engine = M1507PlausibilityAdjudicator()
        self._request_adapter = TypeAdapter(AdjudicateComplexActivityPlausibilityRequest)

    def validate_request(self, request: object) -> AdjudicateComplexActivityPlausibilityRequest:
        return self._request_adapter.validate_python(request, strict=True)

    def _execute_validated(
        self, request: AdjudicateComplexActivityPlausibilityRequest
    ) -> ComplexActivityPlausibilityAdjudicationResult:
        return self._engine.adjudicate(request)

    def execute(self, request: object) -> ComplexActivityPlausibilityAdjudicationResult:
        return self._execute_validated(self.validate_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityPlausibilityAdjudicationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1507Service"]
