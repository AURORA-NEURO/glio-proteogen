"""Thin stateless service for M01-07."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_07 import RouteSupportRequest, SupportRoutingResult
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.engine import (
    M0107SupportRouter,
    preflight_support_routing_authorization,
)

_REQUEST_ADAPTER: Final[TypeAdapter[RouteSupportRequest]] = TypeAdapter(RouteSupportRequest)


class M0107Service:
    """Preflight, revalidate, and delegate one support-routing request."""

    __slots__ = ("_router",)

    def __init__(self, router: M0107SupportRouter | None = None) -> None:
        self._router = router or M0107SupportRouter()

    @staticmethod
    def validate_request(request: object) -> RouteSupportRequest:
        preflight_support_routing_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> SupportRoutingResult:
        return self._router.route(self.validate_request(request))


__all__ = ["M0107Service"]
