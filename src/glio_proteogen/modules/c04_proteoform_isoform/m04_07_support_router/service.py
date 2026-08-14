"""Stateless application boundary for M04-07 proteoform support routing."""

from glio_proteogen.contracts.m04_07 import (
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router.engine import (
    M0407ProteoformSupportRouterEngine,
    _prepare_support_request_candidate,
    _validate_prepared_request,
)


class M0407Service:
    """Authorize, strictly validate, and route one immutable request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0407ProteoformSupportRouterEngine | None = None,
    ) -> None:
        self._engine = engine or M0407ProteoformSupportRouterEngine()

    @staticmethod
    def validate_request(request: object) -> RouteProteoformSupportRequest:
        return _validate_prepared_request(_prepare_support_request_candidate(request))

    def execute(self, request: object) -> ProteoformSupportRouteResult:
        return self._engine.route(request)

    def _execute_validated(
        self,
        request: RouteProteoformSupportRequest,
    ) -> ProteoformSupportRouteResult:
        """Execute only for the plugin's unforgeable validated capability."""

        return self._engine._route_validated(request)


__all__ = ["M0407Service"]
