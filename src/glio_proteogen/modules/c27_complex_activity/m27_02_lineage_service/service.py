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
        return self._resolver.resolve(request)

    def replay(self, result: ComplexActivityLineageResult) -> ComplexActivityLineageResult:
        return self._resolver.replay(result)

    def verify(
        self,
        result: ComplexActivityLineageResult,
        request: ResolveComplexActivityLineageRequest | None = None,
    ) -> ComplexActivityLineageResult:
        if request is not None:
            expected = self.execute(request)
            if expected.model_dump(mode="json") != result.model_dump(mode="json"):
                raise ValueError("lineage replay mismatch")  # noqa: TRY003
            return result
        try:
            return self.replay(result)
        except M2702ReplayError:
            return False  # type: ignore[return-value]


__all__ = ["M2702Service"]
