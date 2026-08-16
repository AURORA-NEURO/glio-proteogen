"""Strict parse-once plugin boundary for provisional M25-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_05 import (
    M2505_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteotypeSubgroupEquityRequest,
    ProteotypeSubgroupEvaluationResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2505_authorization

if TYPE_CHECKING:
    from .service import M2505Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeSubgroupEquityRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M25-05",
    title="Subgroup equity evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "identity, consent, treatment, or clinical eligibility inference",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or unsupported-to-negative conversion",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class SubgroupEquitySubmission:
    """Opaque submission wrapper for strict request validation."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2505Request:
    """Opaque capability proving strict M25-05 request validation."""

    request: EvaluateProteotypeSubgroupEquityRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-05 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-05 validation requires a subgroup-equity submission")


class M2505Plugin(ModulePlugin[object, ValidatedM2505Request, ProteotypeSubgroupEvaluationResult]):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2505Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2505Request:
        if not isinstance(request, SubgroupEquitySubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2505_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2505_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2505Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM2505Request,
    ) -> ProteotypeSubgroupEvaluationResult:
        if not isinstance(request, ValidatedM2505Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def replay(
        self,
        result: ProteotypeSubgroupEvaluationResult,
    ) -> ProteotypeSubgroupEvaluationResult:
        return self._service.verify_replay(result)


__all__ = ["M2505Plugin", "SubgroupEquitySubmission", "ValidatedM2505Request"]
