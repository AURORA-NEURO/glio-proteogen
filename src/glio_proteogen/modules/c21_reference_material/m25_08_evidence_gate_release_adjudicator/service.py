"""Typed service facade for M25-08."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_08 import (
    M2508_MAX_CANONICAL_REQUEST_BYTES,
    M2508_MAX_CANONICAL_RESULT_BYTES,
    AdjudicateProteotypeEvidenceGateRequest,
    ProteotypeEvidenceGateResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2508Engine

_REQUEST_ADAPTER = TypeAdapter(AdjudicateProteotypeEvidenceGateRequest)
_RESULT_ADAPTER = TypeAdapter(ProteotypeEvidenceGateResult)


class M2508Service:
    """Stable service seam over the stateless M25-08 engine."""

    def __init__(self, engine: M2508Engine | None = None) -> None:
        self._engine = engine or M2508Engine()

    def validate_request(self, candidate: object) -> AdjudicateProteotypeEvidenceGateRequest:
        if isinstance(candidate, (bytes, bytearray, str)):
            decoded = strict_json_loads(candidate, max_bytes=M2508_MAX_CANONICAL_REQUEST_BYTES)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        if isinstance(candidate, Mapping):
            return _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(dict(candidate)), strict=True
            )
        return self._engine.validate_request(candidate)

    def execute(self, request: object) -> ProteotypeEvidenceGateResult:
        return self._engine.evaluate(self.validate_request(request))

    def _execute_validated(
        self, request: AdjudicateProteotypeEvidenceGateRequest
    ) -> ProteotypeEvidenceGateResult:
        return self._engine.evaluate(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeEvidenceGateResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2508_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(result, Mapping):
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(dict(result)), strict=True)
        else:
            typed = cast("ProteotypeEvidenceGateResult", result)
        return self._engine.verify(typed, replay=replay)


__all__ = ["M2508Service"]
