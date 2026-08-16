"""Application service boundary for M13-03."""

from glio_proteogen.contracts.m13_03 import (
    ConstructProteotypeMechanisticFeaturesRequest,
    ProteotypeMechanisticFeatureResult,
)

from .engine import (
    M1303MechanisticFeatureEngine,
    _validated_request,
)


class M1303Service:
    """Validate, execute, and expose replay-safe M13-03 operations."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1303MechanisticFeatureEngine | None = None) -> None:
        self._engine = engine or M1303MechanisticFeatureEngine()

    @staticmethod
    def validate_request(request: object) -> ConstructProteotypeMechanisticFeaturesRequest:
        return _validated_request(request)

    def execute(self, request: object) -> ProteotypeMechanisticFeatureResult:
        return self._engine.compute(request)


__all__ = ["M1303Service"]
