"""Strict parse-once plugin boundary for provisional M24-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_03 import (
    M2403_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelInternalBenchmarkResult,
    RunBiomarkerPanelInternalBenchmarkRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2403_authorization

if TYPE_CHECKING:
    from .service import M2403Service

_REQUEST_ADAPTER: Final = TypeAdapter(RunBiomarkerPanelInternalBenchmarkRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-03",
    title="Internal benchmark and ablation (provisional)",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S3",
    gate="G2",
    prohibited_outputs=(
        "biomarker-panel biological estimate",
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
class ValidatedM2403Request:
    """Opaque capability proving strict M24-03 request validation."""

    request: RunBiomarkerPanelInternalBenchmarkRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-03 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-03 validation requires a benchmark submission")


class M2403Plugin(
    ModulePlugin[object, ValidatedM2403Request, BiomarkerPanelInternalBenchmarkResult]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2403Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2403Request:
        if not isinstance(request, BenchmarkSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2403_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2403_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2403Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM2403Request,
    ) -> BiomarkerPanelInternalBenchmarkResult:
        if not isinstance(request, ValidatedM2403Request):
            raise _InvalidExecutionTokenError
        return self._service.generate(request.request)

    def replay(
        self,
        result: BiomarkerPanelInternalBenchmarkResult,
    ) -> BiomarkerPanelInternalBenchmarkResult:
        return self._service.replay(result)


__all__ = ["BenchmarkSubmission", "M2403Plugin", "ValidatedM2403Request"]
