"""Typed SDK facade preserving the M26-04 service canonical boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .service import M2604Service

if TYPE_CHECKING:
    from glio_proteogen.contracts.m26_04 import (
        ProteinSubtypeAccessSurfaceResult,
        PublishProteinSubtypeAccessSurfaceRequest,
    )


class M2604Client:
    """Small typed SDK client with no authority or replay bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2604Service | None = None) -> None:
        self._service = service or M2604Service()

    def validate(self, request: object) -> PublishProteinSubtypeAccessSurfaceRequest:
        return self._service.validate_request(request)

    def publish(self, request: object) -> ProteinSubtypeAccessSurfaceResult:
        return self._service.publish(request)

    def verify(self, result: object) -> ProteinSubtypeAccessSurfaceResult:
        return self._service.replay(result)

    def publish_json(self, request: PublishProteinSubtypeAccessSurfaceRequest) -> dict[str, Any]:
        return self.publish(request).model_dump(mode="json")


__all__ = ["M2604Client"]
