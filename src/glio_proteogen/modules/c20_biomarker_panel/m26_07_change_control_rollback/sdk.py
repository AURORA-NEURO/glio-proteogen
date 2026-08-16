"""Typed SDK facade preserving the M26-07 service and replay boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .service import M2607ChangeControlService

if TYPE_CHECKING:
    from glio_proteogen.contracts.m26_07 import (
        ControlProteinSubtypeChangeRequest,
        ProteinSubtypeChangeControlResult,
    )


class M2607Client:
    """Small typed SDK client with no authority or replay bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2607ChangeControlService | None = None) -> None:
        self._service = service or M2607ChangeControlService()

    def validate(self, request: object) -> ControlProteinSubtypeChangeRequest:
        return self._service.validate_request(request)

    def control(self, request: object) -> ProteinSubtypeChangeControlResult:
        return self._service.control(request)

    def verify(self, result: object) -> ProteinSubtypeChangeControlResult:
        return self._service.verify(result)

    def control_json(self, request: ControlProteinSubtypeChangeRequest) -> dict[str, Any]:
        return self.control(request).model_dump(mode="json")


__all__ = ["M2607Client"]
