"""Application service boundary for M27-02."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_02 import (
    ComplexActivityLineageResult,
    ResolveComplexActivityLineageRequest,
)
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service.engine import (
    M2702LineageResolver,
    M2702ReplayError,
    _plain_value,
    preflight_m2702_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ResolveComplexActivityLineageRequest)


class M2702Service:
    """Validate once, then execute the deterministic lineage resolver."""

    __slots__ = ("_resolver",)

    def __init__(self, resolver: M2702LineageResolver | None = None) -> None:
        self._resolver = resolver or M2702LineageResolver()

    @staticmethod
    def validate_request(request: object) -> ResolveComplexActivityLineageRequest:
        preflight_m2702_authorization(request)
        return _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)

    def execute(self, request: object) -> ComplexActivityLineageResult:
        if type(request) is ResolveComplexActivityLineageRequest:
            preflight_m2702_authorization(request)
            return self._resolver._resolve_validated(request)
        return self._resolver.resolve(self.validate_request(request))

    def execute_validated(
        self, request: ResolveComplexActivityLineageRequest
    ) -> ComplexActivityLineageResult:
        """Execute a request already parsed by an API/CLI/plugin boundary."""

        return self._resolver.resolve_validated(request)

    def replay(self, result: object) -> ComplexActivityLineageResult:
        return self._resolver.replay(result)

    def replay_validated(
        self, result: ComplexActivityLineageResult
    ) -> ComplexActivityLineageResult:
        """Replay a result already parsed by an API/CLI boundary."""

        return self._resolver.replay(result)


__all__ = ["M2702ReplayError", "M2702Service"]
