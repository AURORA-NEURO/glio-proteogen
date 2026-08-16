"""Service seam for M16-07 validation, execution, and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_07 import (
    ExportProteinRnaDiscordanceDownstreamContractRequest,
    ProteinRnaDiscordanceDownstreamExportResult,
)

from .engine import M1607ExportEngine


class M1607Service:
    """Typed service boundary shared by plugin, API, and CLI."""

    def __init__(self) -> None:
        self._engine = M1607ExportEngine()
        self._request_adapter = TypeAdapter(ExportProteinRnaDiscordanceDownstreamContractRequest)

    def validate_request(
        self, request: object
    ) -> ExportProteinRnaDiscordanceDownstreamContractRequest:
        return self._request_adapter.validate_python(request, strict=True)

    def _execute_validated(
        self, request: ExportProteinRnaDiscordanceDownstreamContractRequest
    ) -> ProteinRnaDiscordanceDownstreamExportResult:
        return self._engine.export(request)

    def execute(self, request: object) -> ProteinRnaDiscordanceDownstreamExportResult:
        return self._execute_validated(self.validate_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceDownstreamExportResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1607Service"]
