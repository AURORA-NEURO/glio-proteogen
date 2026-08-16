"""Stateless service boundary for provisional M09-02."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltM0902Result, M0902RepresentationConstructor

if TYPE_CHECKING:
    from glio_proteogen.contracts.m09_02 import (
        ConstructComplexActivityRepresentationRequest,
    )


class M0902Service:
    """Validate, construct, replay, and execute one M09-02 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0902RepresentationConstructor | None = None) -> None:
        self._engine = engine or M0902RepresentationConstructor()

    def validate_request(self, request: object) -> ConstructComplexActivityRepresentationRequest:
        return self._engine.validate_request(request)

    def construct(self, request: object) -> BuiltM0902Result:
        return self._engine.construct(request)

    def verify(self, result: object, canonical_bytes: bytes | None = None) -> bool:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltM0902Result:
        return self._engine.execute(request)


__all__ = ["M0902Service"]
