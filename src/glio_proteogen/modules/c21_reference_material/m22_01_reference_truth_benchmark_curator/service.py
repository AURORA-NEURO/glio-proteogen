"""Strict service seam for provisional M22-01 curation."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_01 import (
    M2201_MAX_CANONICAL_REQUEST_BYTES,
    CurateProteinRnaDiscordanceReferenceTruthRequest,
    ProteinRnaDiscordanceReferenceTruthResult,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    M2201ReferenceTruthBenchmarkCurator,
    preflight_m2201_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(CurateProteinRnaDiscordanceReferenceTruthRequest)


class M2201Service:
    """Authorize, strictly validate, curate, and replay one request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2201ReferenceTruthBenchmarkCurator | None = None) -> None:
        self._engine = engine or M2201ReferenceTruthBenchmarkCurator()

    def validate_request(
        self,
        request: object,
    ) -> CurateProteinRnaDiscordanceReferenceTruthRequest:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M2201_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2201_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(request, strict=True)
        preflight_m2201_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def curate(
        self,
        request: object,
    ) -> ProteinRnaDiscordanceReferenceTruthResult:
        return self._engine.curate(request)

    def verify_replay(
        self,
        result: ProteinRnaDiscordanceReferenceTruthResult,
    ) -> ProteinRnaDiscordanceReferenceTruthResult:
        return self._engine.verify_replay(result)


__all__ = ["M2201Service"]
