"""Strict parse-once plugin boundary for provisional M24-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_04 import (
    M2404_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelExternalTransportResult,
    EvaluateBiomarkerPanelExternalTransportRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2404_authorization

if TYPE_CHECKING:
    from .service import M2404Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelExternalTransportRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-04",
    title="External transport evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "biomarker-panel biological or clinical conclusion",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class ExternalTransportSubmission:
    """Opaque submission wrapper for strict request validation."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2404Request:
    """Opaque capability proving strict M24-04 request validation."""

    request: EvaluateBiomarkerPanelExternalTransportRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-04 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-04 validation requires an external transport submission")


class M2404Plugin(
    ModulePlugin[object, ValidatedM2404Request, BiomarkerPanelExternalTransportResult]
):
    """Expose validate-then-evaluate without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2404Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2404Request:
        if not isinstance(request, ExternalTransportSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2404_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2404_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2404Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2404Request) -> BiomarkerPanelExternalTransportResult:
        if not isinstance(request, ValidatedM2404Request):
            raise _InvalidExecutionTokenError
        return self._service.generate(request.request)

    def replay(
        self, result: BiomarkerPanelExternalTransportResult
    ) -> BiomarkerPanelExternalTransportResult:
        return self._service.replay(result)


__all__ = ["ExternalTransportSubmission", "M2404Plugin", "ValidatedM2404Request"]
