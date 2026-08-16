"""Service seam for the provisional M24-04 transport boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_04 import (
    BiomarkerPanelExternalTransportResult,
    EvaluateBiomarkerPanelExternalTransportRequest,
)

from .engine import M2404ExternalTransportEngine, preflight_m2404_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelExternalTransportRequest)


class M2404Service:
    """Validate, evaluate, and replay M24-04 requests through one engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2404ExternalTransportEngine | None = None) -> None:
        self._engine = engine or M2404ExternalTransportEngine()

    def validate_request(self, request: object) -> EvaluateBiomarkerPanelExternalTransportRequest:
        if isinstance(request, bytes | bytearray | str):
            typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2404_authorization(typed)
        return typed

    def generate(self, request: object) -> BiomarkerPanelExternalTransportResult:
        preflight_m2404_authorization(request)
        return self._engine.generate(request)

    def replay(
        self, result: BiomarkerPanelExternalTransportResult
    ) -> BiomarkerPanelExternalTransportResult:
        return self._engine.replay(result)


__all__ = ["M2404Service"]
