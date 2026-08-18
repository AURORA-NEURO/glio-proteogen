"""Service seam for the provisional M23-07 operational evaluator."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_07 import (
    EvaluateVariantPeptideHumanFactorsRequest,
    VariantPeptideHumanFactorsResult,
)

from .engine import M2307OperationalEngine, preflight_m2307_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateVariantPeptideHumanFactorsRequest)


class M2307Service:
    """Validate, evaluate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2307OperationalEngine | None = None) -> None:
        self._engine = engine or M2307OperationalEngine()

    def validate_request(self, request: object) -> EvaluateVariantPeptideHumanFactorsRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2307_authorization(typed)
        return typed

    def evaluate(self, request: object) -> VariantPeptideHumanFactorsResult:
        return self._engine.generate(self.validate_request(request))

    def replay(
        self,
        result: VariantPeptideHumanFactorsResult,
    ) -> VariantPeptideHumanFactorsResult:
        return self._engine.replay(result)


__all__ = ["M2307Service"]
