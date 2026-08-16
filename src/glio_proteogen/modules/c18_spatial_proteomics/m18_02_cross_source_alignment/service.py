"""Service seam for provisional M18-02 source alignment."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_02 import (
    M1802_MAX_CANONICAL_REQUEST_BYTES,
    AlignBiomarkerPanelSourcesRequest,
    BiomarkerPanelAlignmentResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1802CrossSourceAlignmentEngine

_REQUEST_ADAPTER: Final = TypeAdapter(AlignBiomarkerPanelSourcesRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelAlignmentResult)


class M1802Service:
    """Validate once, align deterministically, and verify replay."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1802CrossSourceAlignmentEngine()

    def validate_request(self, request: object) -> AlignBiomarkerPanelSourcesRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1802_MAX_CANONICAL_REQUEST_BYTES)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> BiomarkerPanelAlignmentResult:
        return self._engine.infer(self.validate_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelAlignmentResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M1802_MAX_CANONICAL_REQUEST_BYTES)
            validated = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(result, Mapping):
            validated = _RESULT_ADAPTER.validate_json(canonical_json_bytes(result), strict=True)
        else:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._engine.verify(validated, replay=replay)

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M18-02",
            title="cross-source alignment and reconciliation (provisional)",
            version="0.1.0-provisional",
            owner="Bioinformatics",
            safety_class="S2",
            gate="G1",
            prohibited_outputs=(
                "generic all-omics fusion, kinase activity, treatment recommendation",
                "identity/consent inference or unsupported-to-negative conversion",
                "upstream mutation, relabeling, or disagreement erasure",
            ),
        )


__all__ = ["M1802Service"]
