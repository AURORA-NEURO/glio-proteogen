"""Service boundary for provisional M15-05 temporal replay."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m15_05 import (
    ComplexActivityLongitudinalEvolutionResult,
    ModelComplexActivityLongitudinalEvolutionRequest,
)

from .engine import M1505EvolutionEngine, infer_complex_activity_longitudinal_evolution


class _InvalidM1505RequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-05 request must be a strict request model or mapping")


class M1505Service:
    """Validate and execute M15-05 through one stateless service object."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1505EvolutionEngine()

    def validate_request(
        self,
        candidate: object,
    ) -> ModelComplexActivityLongitudinalEvolutionRequest:
        if type(candidate) is ModelComplexActivityLongitudinalEvolutionRequest:
            return ModelComplexActivityLongitudinalEvolutionRequest.model_validate(
                candidate,
                strict=True,
            )
        if isinstance(candidate, Mapping):
            return ModelComplexActivityLongitudinalEvolutionRequest.model_validate(
                candidate,
                strict=True,
            )
        raise _InvalidM1505RequestError

    def execute(
        self,
        request: ModelComplexActivityLongitudinalEvolutionRequest,
    ) -> ComplexActivityLongitudinalEvolutionResult:
        return self._engine.construct(request)

    def construct(self, candidate: object) -> ComplexActivityLongitudinalEvolutionResult:
        return infer_complex_activity_longitudinal_evolution(candidate)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityLongitudinalEvolutionResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1505Service"]
