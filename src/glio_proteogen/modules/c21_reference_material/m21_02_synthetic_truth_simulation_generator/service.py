"""Service seam for the provisional M21-02 generator."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_02 import (
    ComplexActivitySyntheticTruthResult,
    GenerateComplexActivitySyntheticTruthRequest,
)

from .engine import M2102Engine, preflight_m2102_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateComplexActivitySyntheticTruthRequest)


class M2102Service:
    """Validate, generate, and replay through one stateless engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2102Engine | None = None) -> None:
        self._engine = engine or M2102Engine()

    def validate_request(
        self,
        request: object,
    ) -> GenerateComplexActivitySyntheticTruthRequest:
        preflight_m2102_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def generate(
        self,
        request: GenerateComplexActivitySyntheticTruthRequest,
    ) -> ComplexActivitySyntheticTruthResult:
        return self._engine.generate(request)

    def replay(
        self,
        result: ComplexActivitySyntheticTruthResult,
    ) -> ComplexActivitySyntheticTruthResult:
        return self._engine.replay(result)
