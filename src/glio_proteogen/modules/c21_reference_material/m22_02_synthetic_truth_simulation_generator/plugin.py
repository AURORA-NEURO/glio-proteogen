"""Strict parse-once plugin boundary for provisional M22-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_02 import (
    M2202_MAX_CANONICAL_REQUEST_BYTES,
    GenerateProteinRnaDiscordanceSyntheticTruthRequest,
    ProteinRnaDiscordanceSyntheticTruthResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2202_authorization

if TYPE_CHECKING:
    from .service import M2202Service

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateProteinRnaDiscordanceSyntheticTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M22-02",
    title="Synthetic truth simulation generator (provisional)",
    version="0.1.0-provisional",
    owner="Data engineering",
    safety_class="S3",
    gate="G1",
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
class SyntheticTruthSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2202Request:
    """Opaque capability proving strict M22-02 request validation."""

    request: GenerateProteinRnaDiscordanceSyntheticTruthRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-02 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-02 validation requires a synthetic-truth submission")


class M2202Plugin(
    ModulePlugin[object, ValidatedM2202Request, ProteinRnaDiscordanceSyntheticTruthResult]
):
    """Expose validate-then-generate without a parse or authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2202Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2202Request:
        if not isinstance(request, SyntheticTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2202_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2202_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2202Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2202Request) -> ProteinRnaDiscordanceSyntheticTruthResult:
        if not isinstance(request, ValidatedM2202Request):
            raise _InvalidExecutionTokenError
        return self._service.generate(request.request)

    def replay(
        self,
        result: ProteinRnaDiscordanceSyntheticTruthResult,
    ) -> ProteinRnaDiscordanceSyntheticTruthResult:
        return self._service.verify_replay(result)


__all__ = ["M2202Plugin", "SyntheticTruthSubmission", "ValidatedM2202Request"]
