"""Strict parse-once plugin boundary for provisional M25-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_03 import (
    M2503_MAX_CANONICAL_REQUEST_BYTES,
    ProteotypeInternalBenchmarkResult,
    RunProteotypeInternalBenchmarkRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2503_authorization

if TYPE_CHECKING:
    from .service import M2503Service

_REQUEST_ADAPTER: Final = TypeAdapter(RunProteotypeInternalBenchmarkRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M25-03",
    title="Internal benchmark and ablation (provisional)",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S3",
    gate="G2",
    prohibited_outputs=(
        "proteotype or biological estimate",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class BenchmarkSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2503Request:
    """Opaque capability proving strict M25-03 request validation."""

    request: RunProteotypeInternalBenchmarkRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-03 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-03 validation requires a benchmark submission")


class M2503Plugin(
    ModulePlugin[object, ValidatedM2503Request, ProteotypeInternalBenchmarkResult]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2503Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2503Request:
        if not isinstance(request, BenchmarkSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2503_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2503_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2503Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM2503Request,
    ) -> ProteotypeInternalBenchmarkResult:
        if not isinstance(request, ValidatedM2503Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def replay(
        self,
        result: ProteotypeInternalBenchmarkResult,
    ) -> ProteotypeInternalBenchmarkResult:
        return self._service.verify_replay(result)


__all__ = ["BenchmarkSubmission", "M2503Plugin", "ValidatedM2503Request"]
