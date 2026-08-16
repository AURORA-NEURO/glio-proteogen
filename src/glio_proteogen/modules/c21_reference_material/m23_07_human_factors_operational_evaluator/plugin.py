"""Strict parse-once plugin boundary for provisional M23-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_07 import (
    M2307_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateVariantPeptideHumanFactorsRequest,
    VariantPeptideHumanFactorsResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2307_authorization

if TYPE_CHECKING:
    from .service import M2307Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateVariantPeptideHumanFactorsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M23-07",
    title="Human-factors and operational evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S3",
    gate="G4",
    prohibited_outputs=(
        "variant-peptide or biological estimate",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class HumanFactorsEvaluationSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2307Request:
    """Opaque capability proving strict M23-07 request validation."""

    request: EvaluateVariantPeptideHumanFactorsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M23-07 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M23-07 validation requires a human-factors submission")


class M2307Plugin(
    ModulePlugin[
        object,
        ValidatedM2307Request,
        VariantPeptideHumanFactorsResult,
    ]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2307Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2307Request:
        if not isinstance(request, HumanFactorsEvaluationSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2307_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2307_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2307Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2307Request) -> VariantPeptideHumanFactorsResult:
        if not isinstance(request, ValidatedM2307Request):
            raise _InvalidExecutionTokenError
        return self._service.evaluate(request.request)

    def replay(
        self,
        result: VariantPeptideHumanFactorsResult,
    ) -> VariantPeptideHumanFactorsResult:
        return self._service.replay(result)


__all__ = ["HumanFactorsEvaluationSubmission", "M2307Plugin", "ValidatedM2307Request"]
