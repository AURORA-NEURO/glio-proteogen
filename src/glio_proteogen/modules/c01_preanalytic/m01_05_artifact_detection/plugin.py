"""Strict validate-then-run plugin boundary for M01-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_05 import ArtifactDetectionResult, DetectArtifactsRequest
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads

if TYPE_CHECKING:
    from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.service import (
        M0105Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[DetectArtifactsRequest]] = TypeAdapter(
    DetectArtifactsRequest
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M01-05",
    title="Artifact and contamination detector",
    version="1.0.0",
    owner="Quality engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw assay parsing or payload retention",
        "learned posterior or unconfigured rule synthesis",
        "proteotype or kinase-state inference",
        "missing evidence interpreted as a clear finding",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0105Request:
    request: DetectArtifactsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M01-05 execution requires a validated request token")


class M0105Plugin(ModulePlugin[object, ValidatedM0105Request, ArtifactDetectionResult]):
    """Expose strict parse, validate, and revalidated execution phases."""

    __slots__ = ("_service",)

    def __init__(self, service: M0105Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0105Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0105Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0105Request) -> ArtifactDetectionResult:
        if not isinstance(request, ValidatedM0105Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0105Plugin", "ValidatedM0105Request"]
