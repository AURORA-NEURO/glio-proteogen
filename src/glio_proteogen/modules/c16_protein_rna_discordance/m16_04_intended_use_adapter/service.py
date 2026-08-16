"""Service seam for provisional M16-04 intended-use adaptation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_04 import AdaptProteinRnaDiscordanceIntendedUseRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1604IntendedUseAdapterEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m16_04 import ProteinRnaDiscordanceIntendedUseResult

_REQUEST_ADAPTER = TypeAdapter(AdaptProteinRnaDiscordanceIntendedUseRequest)


class M1604Service:
    """Keep interface execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1604IntendedUseAdapterEngine | None = None) -> None:
        self._engine = engine or M1604IntendedUseAdapterEngine()

    def execute(
        self, request: AdaptProteinRnaDiscordanceIntendedUseRequest
    ) -> ProteinRnaDiscordanceIntendedUseResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> AdaptProteinRnaDiscordanceIntendedUseRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: AdaptProteinRnaDiscordanceIntendedUseRequest
    ) -> ProteinRnaDiscordanceIntendedUseResult:
        return self._engine.infer(request)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinRnaDiscordanceIntendedUseResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1604Service"]

