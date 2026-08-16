"""Strict parse-once plugin boundary for provisional M22-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_07 import (
    M2207_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteinRnaDiscordanceHumanFactorsRequest,
    ProteinRnaDiscordanceHumanFactorsResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2207_authorization

if TYPE_CHECKING:
    from .service import M2207Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinRnaDiscordanceHumanFactorsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M22-07",
    title="Human-factors and operational evaluator (provisional)",
    version="0.1.0-provisional",
    owner="ML engineering",
    safety_class="S3",
    gate="G4",
    prohibited_outputs=(
        "protein-RNA discordance or biological estimate",
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
class ValidatedM2207Request:
    """Opaque capability proving strict M22-07 request validation."""

    request: EvaluateProteinRnaDiscordanceHumanFactorsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-07 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-07 validation requires a human-factors submission")


class M2207Plugin(
    ModulePlugin[
        object,
        ValidatedM2207Request,
        ProteinRnaDiscordanceHumanFactorsResult,
    ]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2207Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2207Request:
        if not isinstance(request, HumanFactorsEvaluationSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2207_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2207_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2207Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2207Request) -> ProteinRnaDiscordanceHumanFactorsResult:
        if not isinstance(request, ValidatedM2207Request):
            raise _InvalidExecutionTokenError
        return self._service.evaluate(request.request)

    def replay(
        self,
        result: ProteinRnaDiscordanceHumanFactorsResult,
    ) -> ProteinRnaDiscordanceHumanFactorsResult:
        return self._service.replay(result)


__all__ = ["HumanFactorsEvaluationSubmission", "M2207Plugin", "ValidatedM2207Request"]
