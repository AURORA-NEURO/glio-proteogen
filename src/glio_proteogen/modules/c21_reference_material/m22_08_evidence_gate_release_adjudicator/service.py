"""Service seam for the provisional M22-08 evidence gate."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_08 import (
    AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    ProteinRnaDiscordanceEvidenceGateResult,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    M2208EvidenceGateEngine,
    preflight_m2208_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateProteinRnaDiscordanceEvidenceGateRequest)


class M2208Service:
    """Validate, adjudicate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2208EvidenceGateEngine | None = None) -> None:
        self._engine = engine or M2208EvidenceGateEngine()

    def validate_request(
        self,
        request: object,
    ) -> AdjudicateProteinRnaDiscordanceEvidenceGateRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=8 * 1024 * 1024)
            preflight_m2208_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(request, strict=True)
        preflight_m2208_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def adjudicate(self, request: object) -> ProteinRnaDiscordanceEvidenceGateResult:
        return self._engine.adjudicate(self.validate_request(request))

    def replay(
        self,
        result: ProteinRnaDiscordanceEvidenceGateResult,
    ) -> ProteinRnaDiscordanceEvidenceGateResult:
        return self._engine.replay(result)


__all__ = ["M2208Service"]
