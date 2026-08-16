"""Strict parse-once plugin boundary for provisional M24-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_07 import (
    M2407_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelHumanFactorsResult,
    EvaluateBiomarkerPanelHumanFactorsRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2407_authorization

if TYPE_CHECKING:
    from .service import M2407Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelHumanFactorsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-07",
    title="Human-factors and operational evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S3",
    gate="G4",
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
class HumanFactorsSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2407Request:
    """Opaque capability proving strict M24-07 request validation."""

    request: EvaluateBiomarkerPanelHumanFactorsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-07 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-07 validation requires a human-factors submission")


class M2407Plugin(ModulePlugin[object, ValidatedM2407Request, BiomarkerPanelHumanFactorsResult]):
    """Expose validate-then-evaluate without a parse or authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2407Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2407Request:
        if not isinstance(request, HumanFactorsSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2407_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2407_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2407Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2407Request) -> BiomarkerPanelHumanFactorsResult:
        if not isinstance(request, ValidatedM2407Request):
            raise _InvalidExecutionTokenError
        return self._service.evaluate(request.request)

    def replay(
        self,
        result: BiomarkerPanelHumanFactorsResult,
    ) -> BiomarkerPanelHumanFactorsResult:
        return self._service.verify_replay(result)


__all__ = ["HumanFactorsSubmission", "M2407Plugin", "ValidatedM2407Request"]
