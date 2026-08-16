"""Strict parse-once plugin boundary for provisional M24-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_02 import (
    M2402_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelSyntheticTruthResult,
    GenerateBiomarkerPanelSyntheticTruthRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2402_authorization

if TYPE_CHECKING:
    from .service import M2402Service

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateBiomarkerPanelSyntheticTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-02",
    title="Synthetic truth simulation generator (provisional)",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S3",
    gate="G1",
    prohibited_outputs=(
        "biomarker panel or biological truth claim",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity or consent inference",
        "unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class SyntheticTruthSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2402Request:
    """Opaque capability proving strict M24-02 request validation."""

    request: GenerateBiomarkerPanelSyntheticTruthRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-02 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-02 validation requires a synthetic-truth submission")


class M2402Plugin(ModulePlugin[object, ValidatedM2402Request, BiomarkerPanelSyntheticTruthResult]):
    """Expose validate-then-generate without a parse or authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2402Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2402Request:
        if not isinstance(request, SyntheticTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2402_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2402_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2402Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2402Request) -> BiomarkerPanelSyntheticTruthResult:
        if not isinstance(request, ValidatedM2402Request):
            raise _InvalidExecutionTokenError
        return self._service.generate(request.request)

    def replay(
        self,
        result: BiomarkerPanelSyntheticTruthResult,
    ) -> BiomarkerPanelSyntheticTruthResult:
        return self._service.verify_replay(result)


__all__ = ["M2402Plugin", "SyntheticTruthSubmission", "ValidatedM2402Request"]
