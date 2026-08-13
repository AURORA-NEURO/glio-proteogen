"""Stateless application boundary for M03-07 protein-inference support routing."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_07 import (
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
)
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router.engine import (
    M0307ProteinInferenceSupportRouterEngine,
    preflight_protein_inference_support_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(RouteProteinInferenceSupportRequest)


class M0307Service:
    """Authorize, strictly validate, and route one immutable request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0307ProteinInferenceSupportRouterEngine | None = None,
    ) -> None:
        self._engine = engine or M0307ProteinInferenceSupportRouterEngine()

    @staticmethod
    def validate_request(request: object) -> RouteProteinInferenceSupportRequest:
        preflight_protein_inference_support_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ProteinInferenceSupportRouteResult:
        return self._engine.route(request)


__all__ = ["M0307Service"]
