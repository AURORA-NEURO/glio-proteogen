"""Strict parse-once plugin boundary for M23-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_01 import (
    M2301_MAX_CANONICAL_REQUEST_BYTES,
    CurateVariantPeptideReferenceTruthRequest,
    VariantPeptideReferenceTruthResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2301_authorization

if TYPE_CHECKING:
    from .service import M2301Service

_REQUEST_ADAPTER: Final = TypeAdapter(CurateVariantPeptideReferenceTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M23-01",
    title="Reference truth and benchmark curator (provisional)",
    version="0.1.0-provisional",
    owner="Data engineering",
    safety_class="S3",
    gate="G0",
    prohibited_outputs=(
        "issuer or review authority authentication",
        "variant peptide, protein, proteoform, subtype, or complex-activity inference",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or missing-evidence inference",
        "unsupported or missing evidence converted to a negative finding",
    ),
)


@dataclass(frozen=True, slots=True)
class ReferenceTruthSubmission:
    """Submission wrapper that keeps the input object opaque until validation."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2301Request:
    """Opaque capability proving strict M23-01 request validation."""

    request: CurateVariantPeptideReferenceTruthRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M23-01 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M23-01 validation requires a reference-truth submission")


class M2301Plugin(ModulePlugin[object, ValidatedM2301Request, VariantPeptideReferenceTruthResult]):
    """Expose M23-01 through validate-then-run without an authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2301Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2301Request:
        if not isinstance(request, ReferenceTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M2301_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_m2301_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2301Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2301Request) -> VariantPeptideReferenceTruthResult:
        if not isinstance(request, ValidatedM2301Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M2301Plugin", "ReferenceTruthSubmission", "ValidatedM2301Request"]
