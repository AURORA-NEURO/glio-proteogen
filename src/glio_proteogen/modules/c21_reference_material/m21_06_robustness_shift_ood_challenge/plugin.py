"""Strict parse-once plugin boundary for provisional M21-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_06 import (
    M2106_MAX_CANONICAL_REQUEST_BYTES,
    ChallengeComplexActivityRobustnessRequest,
    ComplexActivityRobustnessChallengeResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2106_authorization

if TYPE_CHECKING:
    from .service import M2106Service

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeComplexActivityRobustnessRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M21-06",
    title="Robustness, shift, and OOD challenge (provisional)",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "complex-activity or biological estimate",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity or consent inference",
        "unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class RobustnessSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2106Request:
    """Opaque capability proving strict M21-06 request validation."""

    request: ChallengeComplexActivityRobustnessRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M21-06 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M21-06 validation requires a robustness submission")


class M2106Plugin(
    ModulePlugin[object, ValidatedM2106Request, ComplexActivityRobustnessChallengeResult]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2106Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2106Request:
        if not isinstance(request, RobustnessSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2106_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2106_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2106Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM2106Request,
    ) -> ComplexActivityRobustnessChallengeResult:
        if not isinstance(request, ValidatedM2106Request):
            raise _InvalidExecutionTokenError
        return self._service.generate(request.request)

    def replay(
        self,
        result: ComplexActivityRobustnessChallengeResult,
    ) -> ComplexActivityRobustnessChallengeResult:
        return self._service.replay(result)


__all__ = ["M2106Plugin", "RobustnessSubmission", "ValidatedM2106Request"]
