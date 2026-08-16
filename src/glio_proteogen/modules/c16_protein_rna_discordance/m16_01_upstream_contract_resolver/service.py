"""Service seam for provisional M16-01 resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_01 import ResolveProteinRnaDiscordanceUpstreamRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1601UpstreamContractResolverEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m16_01 import ProteinRnaDiscordanceUpstreamResolutionResult

_REQUEST_ADAPTER = TypeAdapter(ResolveProteinRnaDiscordanceUpstreamRequest)


class M1601Service:
    """Keep interface execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1601UpstreamContractResolverEngine | None = None) -> None:
        self._engine = engine or M1601UpstreamContractResolverEngine()

    def execute(
        self, request: ResolveProteinRnaDiscordanceUpstreamRequest
    ) -> ProteinRnaDiscordanceUpstreamResolutionResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> ResolveProteinRnaDiscordanceUpstreamRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: ResolveProteinRnaDiscordanceUpstreamRequest
    ) -> ProteinRnaDiscordanceUpstreamResolutionResult:
        return self._engine.infer(request)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinRnaDiscordanceUpstreamResolutionResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1601Service"]
