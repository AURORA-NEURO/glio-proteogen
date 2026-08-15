"""Stateless application seam for the provisional M06-02 constructor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M0602RepresentationEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m06_02 import BuildProteinRepresentationRequest


class M0602Service:
    """Strictly validate one request; construction is intentionally deferred."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0602RepresentationEngine()

    @staticmethod
    def validate_request(request: object) -> BuildProteinRepresentationRequest:
        return M0602RepresentationEngine.validate_request(request)

    def construct(self, request: object) -> None:
        return self._engine.construct(request)


__all__ = ["M0602Service"]
