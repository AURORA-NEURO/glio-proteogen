"""Stateless application seam for provisional M08-02."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltRepresentation, M0802RepresentationEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m08_02 import (
        ConstructTranscriptProteinRepresentationRequest,
        ConstructTranscriptProteinRepresentationVerification,
    )


class M0802Service:
    """Validate, construct, replay, and execute one representation request."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0802RepresentationEngine()

    @staticmethod
    def validate_request(
        request: object,
    ) -> ConstructTranscriptProteinRepresentationRequest:
        return M0802RepresentationEngine.validate_request(request)

    def construct(self, request: object) -> BuiltRepresentation:
        return self._engine.construct(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ConstructTranscriptProteinRepresentationVerification:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltRepresentation:
        return self._engine.execute(request)


__all__ = ["M0802Service"]
