"""Strict validate-then-run plugin boundary for M03-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_04 import (
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceQualityResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics.engine import (
    preflight_protein_inference_quality_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics.service import (
        M0304Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(ComputeProteinInferenceQualityRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M03-04",
    title="Quality metric computation",
    version="1.0.0",
    owner="Clinical science",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw bytes, accessions, sequences, measurements, or source member identifiers",
        "protein, proteoform, abundance, subtype, proteotype, or complex-activity inference",
        "kinase-state ownership, generic all-omics fusion, or treatment recommendation",
        "upstream evidence mutation, relabeling, disagreement erasure, or missing-as-negative use",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0304Request:
    """Opaque capability holding one immutable validated metadata request."""

    request: ComputeProteinInferenceQualityRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-04 execution requires a validated request token")


class M0304Plugin(ModulePlugin[object, ValidatedM0304Request, ProteinInferenceQualityResult]):
    """Parse strict metadata and grant one typed execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0304Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0304Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M0304_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_protein_inference_quality_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0304Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0304Request) -> ProteinInferenceQualityResult:
        if not isinstance(request, ValidatedM0304Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0304Plugin", "ValidatedM0304Request"]
