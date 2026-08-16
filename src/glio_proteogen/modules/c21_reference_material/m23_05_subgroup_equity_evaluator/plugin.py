"""Strict parse-once plugin boundary for provisional M23-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_05 import (
    M2305_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateVariantPeptideSubgroupEquityRequest,
    VariantPeptideSubgroupEvaluationResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2305_authorization

if TYPE_CHECKING:
    from .service import M2305Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateVariantPeptideSubgroupEquityRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M23-05",
    title="Subgroup equity evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "variant-peptide biological or clinical conclusion",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class EquityEvaluationSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2305Request:
    """Opaque capability proving strict M23-05 request validation."""

    request: EvaluateVariantPeptideSubgroupEquityRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M23-05 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M23-05 validation requires an equity submission")


class M2305Plugin(
    ModulePlugin[
        object,
        ValidatedM2305Request,
        VariantPeptideSubgroupEvaluationResult,
    ]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2305Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2305Request:
        if not isinstance(request, EquityEvaluationSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2305_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2305_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2305Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2305Request) -> VariantPeptideSubgroupEvaluationResult:
        if not isinstance(request, ValidatedM2305Request):
            raise _InvalidExecutionTokenError
        return self._service.evaluate(request.request)

    def replay(
        self,
        result: VariantPeptideSubgroupEvaluationResult,
    ) -> VariantPeptideSubgroupEvaluationResult:
        return self._service.replay(result)


__all__ = ["EquityEvaluationSubmission", "M2305Plugin", "ValidatedM2305Request"]
