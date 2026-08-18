"""Strict parse-once plugin boundary for M21-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_02 import (
    M2102_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivitySyntheticTruthResult,
    GenerateComplexActivitySyntheticTruthRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2102_authorization

if TYPE_CHECKING:
    from .service import M2102Service

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateComplexActivitySyntheticTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M21-02",
    title="Synthetic truth and simulation generator (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S3",
    gate="G1",
    prohibited_outputs=(
        "biological truth or complex-activity inference",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class SyntheticTruthSubmission:
    """Submission wrapper that keeps the opaque request boundary explicit."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2102Request:
    """Opaque capability proving strict M21-02 request validation."""

    request: GenerateComplexActivitySyntheticTruthRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M21-02 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M21-02 validation requires a synthetic-truth submission")


class M2102Plugin(ModulePlugin[object, ValidatedM2102Request, ComplexActivitySyntheticTruthResult]):
    """Expose M21-02 through validate-then-run without an authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2102Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2102Request:
        if not isinstance(request, SyntheticTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M2102_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_m2102_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2102Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2102Request) -> ComplexActivitySyntheticTruthResult:
        if not isinstance(request, ValidatedM2102Request):
            raise _InvalidExecutionTokenError
        return self._service.generate(request.request)

    def replay(
        self,
        result: ComplexActivitySyntheticTruthResult,
    ) -> ComplexActivitySyntheticTruthResult:
        return self._service.replay(result)


__all__ = ["M2102Plugin", "SyntheticTruthSubmission", "ValidatedM2102Request"]
