"""Service boundary for M11-03 strict validation and execution."""

from glio_proteogen.contracts.m11_03 import (
    ConstructVariantPeptideMechanisticFeaturesRequest,
    VariantPeptideMechanisticFeatureResult,
)

from .engine import (
    M1103MechanisticFeatureEngine,
    _validate_request,
)


class M1103Service:
    __slots__ = ("_engine",)

    def __init__(self, engine: M1103MechanisticFeatureEngine | None = None) -> None:
        self._engine = engine or M1103MechanisticFeatureEngine()

    @staticmethod
    def validate_request(request: object) -> ConstructVariantPeptideMechanisticFeaturesRequest:
        return _validate_request(request)

    def execute(self, request: object) -> VariantPeptideMechanisticFeatureResult:
        return self._engine.compute(request)


__all__ = ["M1103Service"]
