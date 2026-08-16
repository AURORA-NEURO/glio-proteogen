"""Service boundary for provisional M15-08 dossier assembly."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m15_08 import (
    AssembleComplexActivityMechanismDossierRequest,
    ComplexActivityMechanismDossierResult,
)

from .engine import M1508MechanismDossierEngine, assemble_complex_activity_mechanism_dossier


class _InvalidM1508RequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-08 request must be a strict request model or mapping")


class M1508Service:
    """Validate and execute M15-08 through one stateless service object."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1508MechanismDossierEngine()

    def validate_request(
        self,
        candidate: object,
    ) -> AssembleComplexActivityMechanismDossierRequest:
        if type(candidate) is AssembleComplexActivityMechanismDossierRequest:
            return AssembleComplexActivityMechanismDossierRequest.model_validate(
                candidate,
                strict=True,
            )
        if isinstance(candidate, Mapping):
            return AssembleComplexActivityMechanismDossierRequest.model_validate(
                candidate,
                strict=True,
            )
        raise _InvalidM1508RequestError

    def execute(
        self,
        request: AssembleComplexActivityMechanismDossierRequest,
    ) -> ComplexActivityMechanismDossierResult:
        return self._engine.construct(request)

    def construct(self, candidate: object) -> ComplexActivityMechanismDossierResult:
        return assemble_complex_activity_mechanism_dossier(candidate)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanismDossierResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1508Service"]
