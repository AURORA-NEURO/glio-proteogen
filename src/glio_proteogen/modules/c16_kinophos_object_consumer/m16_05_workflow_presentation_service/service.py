"""Service seam for M16-05 validation, execution, and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_05 import (
    PresentProteinRnaReviewWorkspaceRequest,
    ProteinRnaDiscordanceReviewWorkspaceResult,
)

from .engine import M1605PresentationEngine


class M1605Service:
    """Typed service boundary shared by plugin, API, and CLI."""

    def __init__(self) -> None:
        self._engine = M1605PresentationEngine()
        self._request_adapter = TypeAdapter(PresentProteinRnaReviewWorkspaceRequest)

    def validate_request(self, request: object) -> PresentProteinRnaReviewWorkspaceRequest:
        return self._request_adapter.validate_python(request, strict=True)

    def _execute_validated(
        self, request: PresentProteinRnaReviewWorkspaceRequest
    ) -> ProteinRnaDiscordanceReviewWorkspaceResult:
        return self._engine.present(request)

    def execute(self, request: object) -> ProteinRnaDiscordanceReviewWorkspaceResult:
        return self._execute_validated(self.validate_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceReviewWorkspaceResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1605Service"]
