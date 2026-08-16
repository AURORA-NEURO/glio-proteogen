"""Service seam for provisional M15-03 feature construction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_03 import ConstructComplexActivityMechanisticFeaturesRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1503FeatureConstructorEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m15_03 import ComplexActivityMechanisticFeatureResult

_REQUEST_ADAPTER = TypeAdapter(ConstructComplexActivityMechanisticFeaturesRequest)


class M1503Service:
    """Keep adapter execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1503FeatureConstructorEngine | None = None) -> None:
        self._engine = engine or M1503FeatureConstructorEngine()

    def execute(
        self, request: ConstructComplexActivityMechanisticFeaturesRequest
    ) -> ComplexActivityMechanisticFeatureResult:
        return self._engine.infer(request)

    def validate_request(
        self, request: object
    ) -> ConstructComplexActivityMechanisticFeaturesRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: ConstructComplexActivityMechanisticFeaturesRequest
    ) -> ComplexActivityMechanisticFeatureResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanisticFeatureResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1503Service"]
