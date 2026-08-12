"""Strict validate-then-run plugin boundary for M02-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_05 import (
    DetectIdentificationArtifactsRequest,
    IdentificationArtifactDetectionResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection.engine import (
    preflight_identification_artifact_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection.service import (
        M0205Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(DetectIdentificationArtifactsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M02-05",
    title="Artifact and contamination detector",
    version="1.0.0",
    owner="Clinical science",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "protein-subtype, proteotype, or biological inference",
        "kinase-state ownership or generic all-omics fusion",
        "upstream identity, consent, or evidence mutation",
        "missing or unsupported evidence interpreted as a negative finding",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0205Request:
    request: DetectIdentificationArtifactsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M02-05 execution requires a validated request token")


class M0205Plugin(
    ModulePlugin[
        object,
        ValidatedM0205Request,
        IdentificationArtifactDetectionResult,
    ]
):
    __slots__ = ("_service",)

    def __init__(self, service: M0205Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0205Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_identification_artifact_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0205Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM0205Request,
    ) -> IdentificationArtifactDetectionResult:
        if not isinstance(request, ValidatedM0205Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0205Plugin", "ValidatedM0205Request"]
