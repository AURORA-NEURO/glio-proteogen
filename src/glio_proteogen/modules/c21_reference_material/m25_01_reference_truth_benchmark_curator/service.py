"""Stateless M25-01 service boundary."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_01.v1 import (
    CurateProteotypeReferenceTruthRequest,
    ProteotypeReferenceTruthResult,
)

from .engine import (
    M2501ReferenceTruthBenchmarkCurator,
    preflight_m2501_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(CurateProteotypeReferenceTruthRequest)


class M2501Service:
    """Authorize and strictly validate before curating caller material."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M2501ReferenceTruthBenchmarkCurator | None = None,
    ) -> None:
        self._engine = engine or M2501ReferenceTruthBenchmarkCurator()

    @staticmethod
    def validate_request(request: object) -> CurateProteotypeReferenceTruthRequest:
        preflight_m2501_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ProteotypeReferenceTruthResult:
        return self._engine.curate(request)

    def verify_replay(
        self,
        result: ProteotypeReferenceTruthResult,
    ) -> ProteotypeReferenceTruthResult:
        return self._engine.verify_replay(result)


__all__ = ["M2501Service"]
