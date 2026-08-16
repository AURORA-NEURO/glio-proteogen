"""Typed SDK facade preserving the M26-08 service and replay boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .service import M2608RetirementService

if TYPE_CHECKING:
    from glio_proteogen.contracts.m26_08 import (
        ProteinSubtypeRetirementResult,
        RetireProteinSubtypeServiceRequest,
    )


class M2608Client:
    """Small typed SDK client with no authority or replay bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2608RetirementService | None = None) -> None:
        self._service = service or M2608RetirementService()

    def validate(self, request: object) -> RetireProteinSubtypeServiceRequest:
        return self._service.validate_request(request)

    def retire(self, request: object) -> ProteinSubtypeRetirementResult:
        return self._service.retire(request)

    def verify(self, result: object) -> ProteinSubtypeRetirementResult:
        return self._service.verify(result)

    def retire_json(self, request: RetireProteinSubtypeServiceRequest) -> dict[str, Any]:
        return self.retire(request).model_dump(mode="json")


__all__ = ["M2608Client"]
