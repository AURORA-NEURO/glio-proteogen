"""Typed SDK facade preserving the M28-04 service boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .service import M2804Service

if TYPE_CHECKING:
    from glio_proteogen.contracts.m28_04 import (
        ProteinRnaDiscordanceAccessSurfaceResult,
        PublishProteinRnaDiscordanceAccessSurfaceRequest,
    )


class M2804Client:
    """Small typed SDK client with no authority or replay bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2804Service | None = None) -> None:
        self._service = service or M2804Service()

    def validate(self, request: object) -> PublishProteinRnaDiscordanceAccessSurfaceRequest:
        return self._service.validate_request(request)

    def publish(self, request: object) -> ProteinRnaDiscordanceAccessSurfaceResult:
        return self._service.publish(request)

    def verify(self, result: object) -> ProteinRnaDiscordanceAccessSurfaceResult:
        return self._service.replay(result)

    def publish_json(self, request: object) -> dict[str, Any]:
        return self.publish(request).model_dump(mode="json")


__all__ = ["M2804Client"]
