"""Service boundary for provisional M14-05 temporal replay."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m14_05 import (
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    ProteinSubtypeLongitudinalEvolutionResult,
)

from .engine import (
    M1405EvolutionEngine,
    infer_protein_subtype_longitudinal_evolution,
)


class _InvalidM1405RequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M14-05 request must be a strict request model or mapping")


class M1405Service:
    """Validate and execute M14-05 through one stateless service object."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1405EvolutionEngine()

    def validate_request(
        self,
        candidate: object,
    ) -> ModelProteinSubtypeLongitudinalEvolutionRequest:
        if type(candidate) is ModelProteinSubtypeLongitudinalEvolutionRequest:
            return ModelProteinSubtypeLongitudinalEvolutionRequest.model_validate(
                candidate,
                strict=True,
            )
        if isinstance(candidate, Mapping):
            return ModelProteinSubtypeLongitudinalEvolutionRequest.model_validate(
                candidate,
                strict=True,
            )
        raise _InvalidM1405RequestError

    def execute(
        self,
        request: ModelProteinSubtypeLongitudinalEvolutionRequest,
    ) -> ProteinSubtypeLongitudinalEvolutionResult:
        return self._engine.construct(request)

    def construct(self, candidate: object) -> ProteinSubtypeLongitudinalEvolutionResult:
        return infer_protein_subtype_longitudinal_evolution(candidate)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeLongitudinalEvolutionResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1405Service"]
