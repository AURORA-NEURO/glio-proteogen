"""Application service for M12-03 mechanistic feature construction."""

from glio_proteogen.contracts.m12_03 import (
    BiomarkerPanelMechanisticFeatureResult,
    ConstructBiomarkerPanelMechanisticFeaturesRequest,
)
from .engine import (
    M1203MechanisticFeatureEngine,
    _validate_request,
)


class M1203Service:
    """Validate exactly once, then execute the deterministic feature constructor."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1203MechanisticFeatureEngine | None = None) -> None:
        self._engine = engine or M1203MechanisticFeatureEngine()

    @staticmethod
    def validate_request(request: object) -> ConstructBiomarkerPanelMechanisticFeaturesRequest:
        return _validate_request(request)

    def execute(self, request: object) -> BiomarkerPanelMechanisticFeatureResult:
        return self._engine.compute(request)


__all__ = ["M1203Service"]
