"""Stateless service boundary for M21-01 reference curation."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_01.v1 import (
    ComplexActivityReferenceTruthResult,
    CurateComplexActivityReferenceTruthRequest,
)

from .engine import M2101ReferenceTruthBenchmarkCurator, preflight_m2101_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(CurateComplexActivityReferenceTruthRequest)


class M2101Service:
    """Authorize and strictly validate before curating a package."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M2101ReferenceTruthBenchmarkCurator | None = None,
    ) -> None:
        self._engine = engine or M2101ReferenceTruthBenchmarkCurator()

    @staticmethod
    def validate_request(request: object) -> CurateComplexActivityReferenceTruthRequest:
        preflight_m2101_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ComplexActivityReferenceTruthResult:
        return self._engine.curate(request)

    def verify_replay(
        self,
        result: ComplexActivityReferenceTruthResult,
    ) -> ComplexActivityReferenceTruthResult:
        return self._engine.verify_replay(result)


__all__ = ["M2101Service"]
