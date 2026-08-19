"""Strict service boundary for provisional M24-02 generation."""

from __future__ import annotations

import json
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_02 import (
    M2402_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelSyntheticTruthResult,
    GenerateBiomarkerPanelSyntheticTruthRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2402SyntheticTruthGenerator, preflight_m2402_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateBiomarkerPanelSyntheticTruthRequest)


class M2402Service:
    """Parse once, evaluate once, and expose semantic replay verification."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2402SyntheticTruthGenerator | None = None) -> None:
        self._engine = engine or M2402SyntheticTruthGenerator()

    def validate_request(self, request: object) -> GenerateBiomarkerPanelSyntheticTruthRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M2402_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2402_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2402_authorization(typed)
        return typed

    def evaluate(self, request: object) -> BiomarkerPanelSyntheticTruthResult:
        return self._engine.evaluate(self.validate_request(request))

    def verify_replay(
        self, result: BiomarkerPanelSyntheticTruthResult
    ) -> BiomarkerPanelSyntheticTruthResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: BiomarkerPanelSyntheticTruthResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2402Service"]
