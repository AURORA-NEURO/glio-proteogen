"""Strict parse-once plugin boundary for provisional M22-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_01 import (
    M2201_MAX_CANONICAL_REQUEST_BYTES,
    CurateProteinRnaDiscordanceReferenceTruthRequest,
    ProteinRnaDiscordanceReferenceTruthResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2201_authorization

if TYPE_CHECKING:
    from .service import M2201Service

_REQUEST_ADAPTER: Final = TypeAdapter(CurateProteinRnaDiscordanceReferenceTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M22-01",
    title="Protein-RNA discordance reference truth curator (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S3",
    gate="G0",
    prohibited_outputs=(
        "protein-RNA discordance biological truth claim",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity or consent inference",
        "unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class ReferenceTruthSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2201Request:
    """Opaque capability proving strict M22-01 request validation."""

    request: CurateProteinRnaDiscordanceReferenceTruthRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-01 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-01 validation requires a reference-truth submission")


class M2201Plugin(
    ModulePlugin[object, ValidatedM2201Request, ProteinRnaDiscordanceReferenceTruthResult]
):
    """Expose validate-then-curate without a parse or authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2201Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2201Request:
        if not isinstance(request, ReferenceTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2201_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2201_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2201Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2201Request) -> ProteinRnaDiscordanceReferenceTruthResult:
        if not isinstance(request, ValidatedM2201Request):
            raise _InvalidExecutionTokenError
        return self._service.curate(request.request)

    def replay(
        self,
        result: ProteinRnaDiscordanceReferenceTruthResult,
    ) -> ProteinRnaDiscordanceReferenceTruthResult:
        return self._service.verify_replay(result)


__all__ = ["M2201Plugin", "ReferenceTruthSubmission", "ValidatedM2201Request"]
