"""Strict parse-once M25-01 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_01 import (
    M2501_MAX_CANONICAL_REQUEST_BYTES,
    CurateProteotypeReferenceTruthRequest,
    ProteotypeReferenceTruthResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2501_authorization

if TYPE_CHECKING:
    from .service import M2501Service

_REQUEST_ADAPTER: Final = TypeAdapter(CurateProteotypeReferenceTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M25-01",
    title="Reference truth and benchmark curator (provisional)",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S3",
    gate="G0",
    prohibited_outputs=(
        "issuer or review authority authentication",
        "proteotype or biological truth inference",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or missing-evidence inference",
        "unsupported or missing evidence converted to a negative finding",
    ),
)


@dataclass(frozen=True, slots=True)
class ReferenceTruthSubmission:
    """Submission wrapper keeping input opaque until strict validation."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2501Request:
    """Opaque capability proving strict M25-01 request validation."""

    request: CurateProteotypeReferenceTruthRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-01 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-01 validation requires a reference-truth submission")


class M2501Plugin(ModulePlugin[object, ValidatedM2501Request, ProteotypeReferenceTruthResult]):
    """Expose M25-01 through validate-then-run without an authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2501Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2501Request:
        if not isinstance(request, ReferenceTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M2501_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_m2501_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2501Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2501Request) -> ProteotypeReferenceTruthResult:
        if not isinstance(request, ValidatedM2501Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M2501Plugin", "ReferenceTruthSubmission", "ValidatedM2501Request"]
