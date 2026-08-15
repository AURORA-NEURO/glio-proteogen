"""Service seam for the provisional M17-07 operation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_07 import (
    M1707_MAX_CANONICAL_REQUEST_BYTES,
    ExportVariantPeptideDownstreamContractRequest,
    VariantPeptideDownstreamExportResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1707DownstreamTypedExportEngine

_REQUEST_ADAPTER: Final = TypeAdapter(ExportVariantPeptideDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideDownstreamExportResult)


class M1707Service:
    """Validate once, execute deterministically, and verify replay."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1707DownstreamTypedExportEngine()

    def validate_request(self, request: object) -> ExportVariantPeptideDownstreamContractRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1707_MAX_CANONICAL_REQUEST_BYTES)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> VariantPeptideDownstreamExportResult:
        return self._execute_validated(self.validate_request(request))

    def _execute_validated(
        self,
        request: ExportVariantPeptideDownstreamContractRequest,
    ) -> VariantPeptideDownstreamExportResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideDownstreamExportResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M1707_MAX_CANONICAL_REQUEST_BYTES)
            validated = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(result, Mapping):
            validated = _RESULT_ADAPTER.validate_json(canonical_json_bytes(result), strict=True)
        else:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._engine.verify(validated, replay=replay)

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M17-07",
            title="downstream typed export (provisional)",
            version="0.1.0-provisional",
            owner="Data engineering",
            safety_class="S2",
            gate="G3",
            prohibited_outputs=(
                "generic all-omics fusion, kinase activity, treatment recommendation",
                "identity/consent inference or unsupported-to-negative conversion",
                "upstream mutation, relabeling, or disagreement erasure",
            ),
        )


__all__ = ["M1707Service"]

