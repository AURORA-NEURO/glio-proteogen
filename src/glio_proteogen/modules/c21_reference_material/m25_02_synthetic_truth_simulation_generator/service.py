"""Service boundary for provisional M25-02 generation and replay."""

from __future__ import annotations

import json
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_02 import (
    GenerateProteotypeSyntheticTruthRequest,
    ProteotypeSyntheticTruthResult,
)

from .engine import (
    M2502AuthorizationError,
    M2502SyntheticTruthGenerator,
    preflight_m2502_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateProteotypeSyntheticTruthRequest)


class M2502Service:
    """Typed and strict-JSON service seam sharing one canonical engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2502SyntheticTruthGenerator | None = None) -> None:
        self._engine = engine or M2502SyntheticTruthGenerator()

    def validate_request(self, request: object) -> GenerateProteotypeSyntheticTruthRequest:
        try:
            if isinstance(request, bytes | bytearray | str):
                typed = _REQUEST_ADAPTER.validate_json(request, strict=True)
            else:
                typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            if isinstance(error, (ValueError, TypeError)):
                raise
            raise M2502AuthorizationError from None
        preflight_m2502_authorization(typed)
        return typed

    def generate(self, request: object) -> ProteotypeSyntheticTruthResult:
        return self._engine.generate(self.validate_request(request))

    def verify_replay(
        self,
        result: ProteotypeSyntheticTruthResult,
    ) -> ProteotypeSyntheticTruthResult:
        return self._engine.verify_replay(result)

    @staticmethod
    def export_json(result: ProteotypeSyntheticTruthResult) -> str:
        return json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


__all__ = ["M2502Service"]




