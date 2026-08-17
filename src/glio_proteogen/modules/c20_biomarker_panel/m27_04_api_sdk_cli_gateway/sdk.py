"""Typed SDK facade preserving the M27-04 service boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .service import M2704Service

if TYPE_CHECKING:
    from glio_proteogen.contracts.m27_04 import (
        ComplexActivityAccessSurfaceResult,
        PublishComplexActivityAccessSurfaceRequest,
    )


class M2704Client:
    """Small typed SDK client with no authority or replay bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2704Service | None = None) -> None:
        self._service = service or M2704Service()

    def validate(self, request: object) -> PublishComplexActivityAccessSurfaceRequest:
        return self._service.validate_request(request)

    def publish(self, request: object) -> ComplexActivityAccessSurfaceResult:
        return self._service.publish(request)

    def verify(self, result: object) -> ComplexActivityAccessSurfaceResult:
        return self._service.replay(result)

    def publish_json(self, request: object) -> dict[str, Any]:
        return self.publish(request).model_dump(mode="json")


__all__ = ["M2704Client"]
