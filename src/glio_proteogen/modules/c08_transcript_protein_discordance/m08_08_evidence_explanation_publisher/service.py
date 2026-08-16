"""Stateless application service for the provisional M08-08 publisher."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltM0808Result, M0808EvidenceExplanationPublisher

if TYPE_CHECKING:
    from glio_proteogen.contracts.m08_08 import (
        PublishTranscriptProteinEvidenceRequest,
        PublishTranscriptProteinEvidenceVerification,
    )


class M0808Service:
    """Validate, publish, replay, and execute one M08-08 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0808EvidenceExplanationPublisher | None = None) -> None:
        self._engine = engine or M0808EvidenceExplanationPublisher()

    def validate_request(self, request: object) -> PublishTranscriptProteinEvidenceRequest:
        return self._engine.validate_request(request)

    def publish(self, request: object) -> BuiltM0808Result:
        return self._engine.publish(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> PublishTranscriptProteinEvidenceVerification:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltM0808Result:
        return self._engine.execute(request)


__all__ = ["M0808Service"]
