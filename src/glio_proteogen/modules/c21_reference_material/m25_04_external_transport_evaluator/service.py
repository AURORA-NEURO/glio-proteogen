"""Service seam for the provisional M25-04 transport evaluator."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_04 import (
    EvaluateProteotypeExternalTransportRequest,
    ProteotypeExternalTransportResult,
)

from .engine import M2504TransportEngine, preflight_m2504_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeExternalTransportRequest)


class M2504Service:
    """Validate, execute, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2504TransportEngine | None = None) -> None:
        self._engine = engine or M2504TransportEngine()

    def validate_request(self, request: object) -> EvaluateProteotypeExternalTransportRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
            preflight_m2504_authorization(typed)
        else:
            preflight_m2504_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return typed

    def execute(self, request: object) -> ProteotypeExternalTransportResult:
        return self._engine.evaluate(self.validate_request(request))

    def verify_replay(
        self,
        result: ProteotypeExternalTransportResult,
    ) -> ProteotypeExternalTransportResult:
        return self._engine.replay(result)


__all__ = ["M2504Service"]
