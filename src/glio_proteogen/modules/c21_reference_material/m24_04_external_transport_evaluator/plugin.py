"""Strict plugin boundary for provisional M24-04 transport evaluation."""

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

_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelExternalTransportRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-04",
    title="External transport evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "biomarker or biological generalization",
        "protein/proteoform/isoform or glioma inference",
        "treatment, kinase, identity or consent inference",
        "unsupported-to-negative conversion",
    ),
)


@dataclass(frozen=True, slots=True)
class ExternalTransportSubmission:
    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2404Request:
    request: EvaluateBiomarkerPanelExternalTransportRequest


class M2404Plugin(
    ModulePlugin[object, ValidatedM2404Request, BiomarkerPanelExternalTransportResult]
):
    __slots__ = ("_service",)

    def __init__(self, service: M2404Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2404Request:
        if not isinstance(request, ExternalTransportSubmission):
            raise TypeError("M24-04 validation requires an external-transport submission")  # noqa: TRY003
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2404_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2404_authorization(decoded)
            candidate = _ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2404Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2404Request) -> BiomarkerPanelExternalTransportResult:
        if not isinstance(request, ValidatedM2404Request):
            raise TypeError("M24-04 execution requires a validated request token")  # noqa: TRY003
        return self._service.evaluate(request.request)

    def replay(
        self, result: BiomarkerPanelExternalTransportResult
    ) -> BiomarkerPanelExternalTransportResult:
        return self._service.verify_replay(result)


__all__ = ["ExternalTransportSubmission", "M2404Plugin", "ValidatedM2404Request"]
