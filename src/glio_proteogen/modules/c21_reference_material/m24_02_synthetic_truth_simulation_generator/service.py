"""Service boundary for provisional M24-02 generation and replay."""

from __future__ import annotations

import json
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_02 import (
    BiomarkerPanelSyntheticTruthResult,
    GenerateBiomarkerPanelSyntheticTruthRequest,
)

from .engine import (
    M2402AuthorizationError,
    M2402SyntheticTruthGenerator,
    preflight_m2402_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateBiomarkerPanelSyntheticTruthRequest)


class M2402Service:
    """Typed and strict-JSON service seam sharing one canonical engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2402SyntheticTruthGenerator | None = None) -> None:
        self._engine = engine or M2402SyntheticTruthGenerator()

    def validate_request(self, request: object) -> GenerateBiomarkerPanelSyntheticTruthRequest:
        try:
            if isinstance(request, bytes | bytearray | str):
                typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
            else:
                typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            if isinstance(error, (ValueError, TypeError)):
                raise
            raise M2402AuthorizationError from None
        preflight_m2402_authorization(typed)
        return typed

    def generate(self, request: object) -> BiomarkerPanelSyntheticTruthResult:
        return self._engine.generate(self.validate_request(request))

    def verify_replay(
        self,
        result: BiomarkerPanelSyntheticTruthResult,
    ) -> BiomarkerPanelSyntheticTruthResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: BiomarkerPanelSyntheticTruthResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2402Service"]
