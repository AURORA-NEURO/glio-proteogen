"""Strict parse-once plugin boundary for provisional M24-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_05 import (
    M2405_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelSubgroupEvaluationResult,
    EvaluateBiomarkerPanelSubgroupEquityRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2405_authorization

if TYPE_CHECKING:
    from .service import M2405Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateBiomarkerPanelSubgroupEquityRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-05",
    title="Subgroup equity evaluator (provisional)",
    version="0.1.0-provisional",
    owner="ML engineering",
    safety_class="S3",
    gate="G3",
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
class SubgroupEvaluationSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2405Request:
    """Opaque capability proving strict M24-05 request validation."""

    request: EvaluateBiomarkerPanelSubgroupEquityRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-05 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-05 validation requires a subgroup-evaluation submission")


class M2405Plugin(
    ModulePlugin[object, ValidatedM2405Request, BiomarkerPanelSubgroupEvaluationResult]
):
    """Expose validate-then-evaluate without a parse or authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2405Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2405Request:
        if not isinstance(request, SubgroupEvaluationSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2405_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2405_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2405Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2405Request) -> BiomarkerPanelSubgroupEvaluationResult:
        if not isinstance(request, ValidatedM2405Request):
            raise _InvalidExecutionTokenError
        return self._service.evaluate(request.request)

    def replay(
        self,
        result: BiomarkerPanelSubgroupEvaluationResult,
    ) -> BiomarkerPanelSubgroupEvaluationResult:
        return self._service.verify_replay(result)


__all__ = ["M2405Plugin", "SubgroupEvaluationSubmission", "ValidatedM2405Request"]
