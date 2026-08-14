"""Strict validate-then-run plugin boundary for M04-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m04_05 import (
    M0405_MAX_CANONICAL_REQUEST_BYTES,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection.service import (
        M0405Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-05",
    title="Proteoform artifact and contamination detector",
    version="1.0.0",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, sequences, accessions, abundance values, or external content",
        "identity, consent, protein, proteoform, isoform, subtype, or PTM inference",
        "protein-RNA discordance, proteogenomic state, proteotype, or subtype emission",
        "kinase-state inference, all-omics fusion, treatment advice, or clinical decisions",
        "upstream mutation, relabeling, missing-as-negative conversion, or model execution",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0405Request:
    request: DetectProteoformArtifactsRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-05 execution requires a validated request token")


class M0405Plugin(ModulePlugin[object, ValidatedM0405Request, ProteoformArtifactDetectionResult]):
    """Grant one immutable M04-05 execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0405Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0405Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0405_MAX_CANONICAL_REQUEST_BYTES,
            )
        typed = self._service.validate_request(candidate)
        return ValidatedM0405Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM0405Request) -> ProteoformArtifactDetectionResult:
        if type(request) is not ValidatedM0405Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0405Plugin", "ValidatedM0405Request"]
