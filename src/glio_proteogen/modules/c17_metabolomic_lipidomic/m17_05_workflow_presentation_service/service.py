"""Service seam for the provisional M17-05 operation."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_05 import (
    M1705_MAX_CANONICAL_REQUEST_BYTES,
    PresentVariantPeptideHumanReviewWorkspaceRequest,
    VariantPeptideHumanReviewWorkspaceResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1705WorkflowPresentationEngine

_REQUEST_ADAPTER: Final = TypeAdapter(PresentVariantPeptideHumanReviewWorkspaceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideHumanReviewWorkspaceResult)


class M1705Service:
    """Validate once, execute deterministically, and verify replay."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1705WorkflowPresentationEngine()

    def validate_request(self, request: object) -> PresentVariantPeptideHumanReviewWorkspaceRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1705_MAX_CANONICAL_REQUEST_BYTES)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> VariantPeptideHumanReviewWorkspaceResult:
        return self._execute_validated(self.validate_request(request))

    def _execute_validated(
        self,
        request: PresentVariantPeptideHumanReviewWorkspaceRequest,
    ) -> VariantPeptideHumanReviewWorkspaceResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideHumanReviewWorkspaceResult:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._engine.verify(validated, replay=replay)

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M17-05",
            title="workflow presentation service (provisional)",
            version="0.1.0-provisional",
            owner="Quality engineering",
            safety_class="S2",
            gate="G4",
            prohibited_outputs=(
                "generic all-omics fusion, kinase activity, treatment recommendation",
                "identity/consent inference or unsupported-to-negative conversion",
                "upstream mutation, relabeling, or disagreement erasure",
            ),
        )


__all__ = ["M1705Service"]

