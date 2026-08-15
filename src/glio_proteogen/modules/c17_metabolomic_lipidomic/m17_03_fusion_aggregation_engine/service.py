"""Service seam for the provisional M17-03 operation."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_03 import (
    M1703_MAX_CANONICAL_REQUEST_BYTES,
    FuseVariantPeptideEvidenceRequest,
    VariantPeptideIntegratedEvidenceResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1703FusionAggregationEngine

_REQUEST_ADAPTER: Final = TypeAdapter(FuseVariantPeptideEvidenceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideIntegratedEvidenceResult)


class M1703Service:
    """Validate once, execute deterministically, and verify replay."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1703FusionAggregationEngine()

    def validate_request(self, request: object) -> FuseVariantPeptideEvidenceRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1703_MAX_CANONICAL_REQUEST_BYTES)
            return _REQUEST_ADAPTER.validate_python(decoded, strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> VariantPeptideIntegratedEvidenceResult:
        return self._execute_validated(self.validate_request(request))

    def _execute_validated(
        self, request: FuseVariantPeptideEvidenceRequest
    ) -> VariantPeptideIntegratedEvidenceResult:
        return self._engine.infer(request)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> VariantPeptideIntegratedEvidenceResult:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._engine.verify(validated, replay=replay)

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M17-03",
            title="fusion and aggregation engine (provisional)",
            version="0.1.0-provisional",
            owner="Bioinformatics",
            safety_class="S2",
            gate="G2",
            prohibited_outputs=(
                "generic all-omics fusion, kinase activity, treatment recommendation",
                "identity/consent inference or unsupported-to-negative conversion",
                "upstream mutation, relabeling, or disagreement erasure",
            ),
        )


__all__ = ["M1703Service"]
