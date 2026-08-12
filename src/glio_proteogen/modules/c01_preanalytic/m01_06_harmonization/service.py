"""Thin stateless service for M01-06."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_06 import HarmonizationResult, HarmonizeObservationsRequest
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.engine import (
    M0106HarmonizationEngine,
    preflight_harmonization_authorization,
)

_REQUEST_ADAPTER: Final[TypeAdapter[HarmonizeObservationsRequest]] = TypeAdapter(
    HarmonizeObservationsRequest
)


class M0106Service:
    """Preflight, revalidate, and delegate one harmonization request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0106HarmonizationEngine | None = None) -> None:
        self._engine = engine or M0106HarmonizationEngine()

    @staticmethod
    def validate_request(request: object) -> HarmonizeObservationsRequest:
        preflight_harmonization_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> HarmonizationResult:
        return self._engine.harmonize(self.validate_request(request))


__all__ = ["M0106Service"]
