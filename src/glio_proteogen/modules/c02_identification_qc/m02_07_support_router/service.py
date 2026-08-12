"""Stateless application boundary for M02-07 joint support routing."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_07 import (
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router.engine import (
    M0207SupportRouterEngine,
    preflight_identification_support_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(RouteIdentificationSupportRequest)


class M0207Service:
    """Authorize, strictly validate, and route one immutable request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0207SupportRouterEngine | None = None) -> None:
        self._engine = engine or M0207SupportRouterEngine()

    @staticmethod
    def validate_request(request: object) -> RouteIdentificationSupportRequest:
        preflight_identification_support_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> IdentificationSupportRouteResult:
        return self._engine.route(request)


__all__ = ["M0207Service"]
