"""Strict validate-then-run plugin boundary for M03-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_05 import (
    M0305_MAX_CANONICAL_REQUEST_BYTES,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection.engine import (
    preflight_protein_inference_artifact_authorization,
    prepare_artifact_request_candidate,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection.service import (
        M0305Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(DetectProteinInferenceArtifactsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M03-05",
    title="Artifact and contamination detector",
    version="1.0.0",
    owner="Data engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw bytes, peptide strings, accessions, sequences, or measurements",
        "protein, proteoform, abundance, subtype, proteotype, or complex-activity inference",
        "calibrated probability, kinase-state ownership, or treatment recommendation",
        "upstream mutation, relabeling, disagreement erasure, or missing-as-negative use",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0305Request:
    """Opaque capability holding one immutable validated metadata request."""

    request: DetectProteinInferenceArtifactsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-05 execution requires a validated request token")


class M0305Plugin(
    ModulePlugin[
        object,
        ValidatedM0305Request,
        ProteinInferenceArtifactDetectionResult,
    ]
):
    """Parse strict metadata and grant one typed execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0305Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0305Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M0305_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_protein_inference_artifact_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(prepare_artifact_request_candidate(decoded)),
                strict=True,
            )
        return ValidatedM0305Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0305Request) -> ProteinInferenceArtifactDetectionResult:
        if not isinstance(request, ValidatedM0305Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0305Plugin", "ValidatedM0305Request"]
