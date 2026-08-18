"""Strict parse-once plugin boundary for provisional M22-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_08 import (
    M2208_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    ProteinRnaDiscordanceEvidenceGateResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2208_authorization

if TYPE_CHECKING:
    from .service import M2208Service

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateProteinRnaDiscordanceEvidenceGateRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M22-08",
    title="Evidence gate and release adjudicator (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S3",
    gate="G5",
    prohibited_outputs=(
        "protein-RNA discordance or biological estimate",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class EvidenceGateSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2208Request:
    """Opaque capability proving strict M22-08 request validation."""

    request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-08 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-08 validation requires an evidence-gate submission")


class M2208Plugin(
    ModulePlugin[
        object,
        ValidatedM2208Request,
        ProteinRnaDiscordanceEvidenceGateResult,
    ]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2208Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2208Request:
        if not isinstance(request, EvidenceGateSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2208_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2208_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2208Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2208Request) -> ProteinRnaDiscordanceEvidenceGateResult:
        if not isinstance(request, ValidatedM2208Request):
            raise _InvalidExecutionTokenError
        return self._service.adjudicate(request.request)

    def replay(
        self,
        result: ProteinRnaDiscordanceEvidenceGateResult,
    ) -> ProteinRnaDiscordanceEvidenceGateResult:
        return self._service.replay(result)


__all__ = ["EvidenceGateSubmission", "M2208Plugin", "ValidatedM2208Request"]
