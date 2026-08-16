"""Strict parse-once plugin boundary for provisional M25-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_02 import (
    M2502_MAX_CANONICAL_REQUEST_BYTES,
    GenerateProteotypeSyntheticTruthRequest,
    ProteotypeSyntheticTruthResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2502_authorization

if TYPE_CHECKING:
    from .service import M2502Service

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateProteotypeSyntheticTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M25-02",
    title="Synthetic truth simulation generator (provisional)",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S3",
    gate="G1",
    prohibited_outputs=(
        "proteotype or biological truth claim",
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
class ValidatedM2502Request:
    """Opaque capability proving strict M25-02 request validation."""

    request: GenerateProteotypeSyntheticTruthRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-02 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-02 validation requires a synthetic-truth submission")


class M2502Plugin(ModulePlugin[object, ValidatedM2502Request, ProteotypeSyntheticTruthResult]):
    """Expose validate-then-generate without a parse or authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2502Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2502Request:
        if not isinstance(request, SyntheticTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2502_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2502_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2502Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2502Request) -> ProteotypeSyntheticTruthResult:
        if not isinstance(request, ValidatedM2502Request):
            raise _InvalidExecutionTokenError
        return self._service.generate(request.request)

    def replay(
        self,
        result: ProteotypeSyntheticTruthResult,
    ) -> ProteotypeSyntheticTruthResult:
        return self._service.verify_replay(result)


__all__ = ["M2502Plugin", "SyntheticTruthSubmission", "ValidatedM2502Request"]
