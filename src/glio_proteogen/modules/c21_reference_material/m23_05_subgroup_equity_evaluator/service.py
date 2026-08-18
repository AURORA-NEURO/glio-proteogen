"""Service seam for the provisional M23-05 subgroup evaluator."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_05 import (
    EvaluateVariantPeptideSubgroupEquityRequest,
    VariantPeptideSubgroupEvaluationResult,
)

from .engine import M2305EquityEngine, preflight_m2305_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateVariantPeptideSubgroupEquityRequest)


class M2305Service:
    """Validate, evaluate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2305EquityEngine | None = None) -> None:
        self._engine = engine or M2305EquityEngine()

    def validate_request(self, request: object) -> EvaluateVariantPeptideSubgroupEquityRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2305_authorization(typed)
        return typed

    def evaluate(self, request: object) -> VariantPeptideSubgroupEvaluationResult:
        return self._engine.generate(self.validate_request(request))

    def replay(
        self,
        result: VariantPeptideSubgroupEvaluationResult,
    ) -> VariantPeptideSubgroupEvaluationResult:
        return self._engine.replay(result)


__all__ = ["M2305Service"]
