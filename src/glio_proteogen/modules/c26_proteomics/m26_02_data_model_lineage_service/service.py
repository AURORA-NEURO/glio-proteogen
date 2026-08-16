"""Stateless service seam for M26-02 validation, execution, and replay."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_02 import (
    BuildProteinSubtypeLineageRequest,
    ProteinSubtypeLineageResult,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.engine import (
    M2602LineageEngine,
    preflight_lineage_authorization,
    verify_lineage_result,
)

_REQUEST_ADAPTER: Final[TypeAdapter[BuildProteinSubtypeLineageRequest]] = TypeAdapter(
    BuildProteinSubtypeLineageRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteinSubtypeLineageResult]] = TypeAdapter(
    ProteinSubtypeLineageResult
)


class M2602LineageService:
    """Preflight, strict-validate, execute, and replay one request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2602LineageEngine | None = None) -> None:
        self._engine = engine or M2602LineageEngine()

    @staticmethod
    def validate_request(request: object) -> BuildProteinSubtypeLineageRequest:
        preflight_lineage_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ProteinSubtypeLineageResult:
        return self._engine.build(self.validate_request(request))

    @staticmethod
    def verify(result: object) -> ProteinSubtypeLineageResult:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        return verify_lineage_result(validated)


__all__ = ["M2602LineageService"]
