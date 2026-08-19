"""Strict service seam for provisional M24-04 transport evaluation."""

from __future__ import annotations

import json
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_04 import (
    M2404_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelExternalTransportResult,
    EvaluateBiomarkerPanelExternalTransportRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2404ExternalTransportEvaluator, preflight_m2404_authorization

_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelExternalTransportRequest)


class M2404Service:
    __slots__ = ("_engine",)

    def __init__(self, engine: M2404ExternalTransportEvaluator | None = None) -> None:
        self._engine = engine or M2404ExternalTransportEvaluator()

    def validate_request(self, request: object) -> EvaluateBiomarkerPanelExternalTransportRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M2404_MAX_CANONICAL_REQUEST_BYTES)
            typed = _ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2404_authorization(request)
            typed = _ADAPTER.validate_python(request, strict=True)
        preflight_m2404_authorization(typed)
        return typed

    def evaluate(self, request: object) -> BiomarkerPanelExternalTransportResult:
        return self._engine.evaluate(self.validate_request(request))

    def verify_replay(
        self, result: BiomarkerPanelExternalTransportResult
    ) -> BiomarkerPanelExternalTransportResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: BiomarkerPanelExternalTransportResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2404Service"]
