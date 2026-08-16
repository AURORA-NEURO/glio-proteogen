"""Service boundary for provisional M14-03 feature construction."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m14_03 import (
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    ProteinSubtypeMechanisticFeatureResult,
)

from .engine import (
    M1403MechanisticFeatureEngine,
    construct_protein_subtype_mechanistic_features,
)


class _InvalidM1403RequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M14-03 request must be a strict request model or mapping")


class M1403Service:
    """Validate and execute M14-03 through one stateless service object."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1403MechanisticFeatureEngine()

    def validate_request(
        self,
        candidate: object,
    ) -> ConstructProteinSubtypeMechanisticFeaturesRequest:
        if type(candidate) is ConstructProteinSubtypeMechanisticFeaturesRequest:
            return ConstructProteinSubtypeMechanisticFeaturesRequest.model_validate(
                candidate,
                strict=True,
            )
        if isinstance(candidate, Mapping):
            return ConstructProteinSubtypeMechanisticFeaturesRequest.model_validate(
                candidate,
                strict=True,
            )
        raise _InvalidM1403RequestError

    def execute(
        self,
        request: ConstructProteinSubtypeMechanisticFeaturesRequest,
    ) -> ProteinSubtypeMechanisticFeatureResult:
        return self._engine.construct(request)

    def construct(self, candidate: object) -> ProteinSubtypeMechanisticFeatureResult:
        return construct_protein_subtype_mechanistic_features(candidate)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanisticFeatureResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1403Service"]
