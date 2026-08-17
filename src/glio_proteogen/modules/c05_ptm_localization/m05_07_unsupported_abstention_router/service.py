"""Stateless application boundary for M05-07 support routing."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_07 import (
    PtmLocalizationSupportRouteResult,
    RoutePtmLocalizationSupportRequest,
)
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router.engine import (  # noqa: E501
    M0507PtmLocalizationSupportEngine,
    _prepare_request,
)

_REQUEST_ADAPTER: Final = TypeAdapter(RoutePtmLocalizationSupportRequest)


class M0507Service:
    """Validate one request, then delegate to the deterministic router."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0507PtmLocalizationSupportEngine | None = None) -> None:
        self._engine = engine or M0507PtmLocalizationSupportEngine()

    @staticmethod
    def validate_request(request: object) -> RoutePtmLocalizationSupportRequest:
        return _REQUEST_ADAPTER.validate_python(_prepare_request(request), strict=True)

    def _execute_validated(
        self,
        request: RoutePtmLocalizationSupportRequest,
    ) -> PtmLocalizationSupportRouteResult:
        return self._engine._route_validated(request)

    def execute(self, request: object) -> PtmLocalizationSupportRouteResult:
        return self._engine.route(request)


__all__ = ["M0507Service"]
