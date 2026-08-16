"""Service seam for M16-02 validation, execution, and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_02 import (
    ProteinRnaDiscordanceAlignmentResult,
    ReconcileCrossSourceAlignmentRequest,
)

from .engine import M1602AlignmentEngine


class M1602Service:
    """Typed service boundary shared by plugin, API, and CLI."""

    def __init__(self) -> None:
        self._engine = M1602AlignmentEngine()
        self._request_adapter = TypeAdapter(ReconcileCrossSourceAlignmentRequest)

    def validate_request(self, request: object) -> ReconcileCrossSourceAlignmentRequest:
        return self._request_adapter.validate_python(request, strict=True)

    def _execute_validated(
        self, request: ReconcileCrossSourceAlignmentRequest
    ) -> ProteinRnaDiscordanceAlignmentResult:
        return self._engine.reconcile(request)

    def execute(self, request: object) -> ProteinRnaDiscordanceAlignmentResult:
        return self._execute_validated(self.validate_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceAlignmentResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1602Service"]
