"""Service seam for the provisional M25-05 evaluator."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_05 import (
    M2505_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteotypeSubgroupEquityRequest,
    ProteotypeSubgroupEvaluationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2505SubgroupEquityEngine, preflight_m2505_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeSubgroupEquityRequest)


class M2505Service:
    """Validate, execute, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2505SubgroupEquityEngine | None = None) -> None:
        self._engine = engine or M2505SubgroupEquityEngine()

    def validate_request(self, request: object) -> EvaluateProteotypeSubgroupEquityRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M2505_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
            preflight_m2505_authorization(typed)
        else:
            preflight_m2505_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return typed

    def execute(self, request: object) -> ProteotypeSubgroupEvaluationResult:
        return self._engine.generate(self.validate_request(request))

    def verify_replay(
        self,
        result: ProteotypeSubgroupEvaluationResult,
    ) -> ProteotypeSubgroupEvaluationResult:
        return self._engine.replay(result)


__all__ = ["M2505Service"]
