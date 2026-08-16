"""Stateless application service for provisional M09-08."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltM0908Result, M0908EvidencePublisher

if TYPE_CHECKING:
    from glio_proteogen.contracts.m09_08 import (
        ComplexActivityEvidencePublicationVerification,
        PublishComplexActivityEvidenceRequest,
    )


class M0908Service:
    """Validate, publish, replay, and execute one M09-08 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0908EvidencePublisher | None = None) -> None:
        self._engine = engine or M0908EvidencePublisher()

    def validate_request(self, request: object) -> PublishComplexActivityEvidenceRequest:
        return self._engine.validate_request(request)

    def publish(self, request: object) -> BuiltM0908Result:
        return self._engine.publish(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ComplexActivityEvidencePublicationVerification:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltM0908Result:
        return self._engine.execute(request)


__all__ = ["M0908Service"]
