"""Service seam for provisional M16-08 monitoring and rollback."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_08 import MonitorProteinRnaTranslationHealthRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1608TranslationMonitoringEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m16_08 import ProteinRnaDiscordanceTranslationHealthResult

_REQUEST_ADAPTER = TypeAdapter(MonitorProteinRnaTranslationHealthRequest)


class M1608Service:
    """Keep interface execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1608TranslationMonitoringEngine | None = None) -> None:
        self._engine = engine or M1608TranslationMonitoringEngine()

    def execute(
        self, request: MonitorProteinRnaTranslationHealthRequest
    ) -> ProteinRnaDiscordanceTranslationHealthResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> MonitorProteinRnaTranslationHealthRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: MonitorProteinRnaTranslationHealthRequest
    ) -> ProteinRnaDiscordanceTranslationHealthResult:
        return self._engine.infer(request)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinRnaDiscordanceTranslationHealthResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1608Service"]
