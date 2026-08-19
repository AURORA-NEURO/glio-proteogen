"""Service seam for the provisional M25-07 evaluator."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_07 import (
    M2507_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteotypeHumanFactorsRequest,
    ProteotypeHumanFactorsResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2507HumanFactorsEngine, preflight_m2507_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeHumanFactorsRequest)


class M2507Service:
    """Validate, execute, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2507HumanFactorsEngine | None = None) -> None:
        self._engine = engine or M2507HumanFactorsEngine()

    def validate_request(self, request: object) -> EvaluateProteotypeHumanFactorsRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M2507_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
            preflight_m2507_authorization(typed)
        else:
            preflight_m2507_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return typed

    def execute(self, request: object) -> ProteotypeHumanFactorsResult:
        return self._engine.generate(self.validate_request(request))

    def verify_replay(
        self,
        result: ProteotypeHumanFactorsResult,
    ) -> ProteotypeHumanFactorsResult:
        return self._engine.replay(result)


__all__ = ["M2507Service"]
