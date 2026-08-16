"""Stateless service boundary for M23-01 reference curation."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_01 import (
    CurateVariantPeptideReferenceTruthRequest,
    VariantPeptideReferenceTruthResult,
)

from .engine import M2301ReferenceTruthBenchmarkCurator, preflight_m2301_authorization

_REQUEST_ADAPTER: Final = TypeAdapter(CurateVariantPeptideReferenceTruthRequest)


class M2301Service:
    """Authorize and strictly validate before curating a package."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2301ReferenceTruthBenchmarkCurator | None = None) -> None:
        self._engine = engine or M2301ReferenceTruthBenchmarkCurator()

    @staticmethod
    def validate_request(request: object) -> CurateVariantPeptideReferenceTruthRequest:
        preflight_m2301_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> VariantPeptideReferenceTruthResult:
        return self._engine.curate(request)

    def verify_replay(
        self,
        result: VariantPeptideReferenceTruthResult,
    ) -> VariantPeptideReferenceTruthResult:
        return self._engine.verify_replay(result)


__all__ = ["M2301Service"]
