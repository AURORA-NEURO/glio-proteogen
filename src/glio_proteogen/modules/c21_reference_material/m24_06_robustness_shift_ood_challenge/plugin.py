"""Strict parse-once plugin boundary for provisional M24-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_06 import (
    M2406_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2406_authorization

if TYPE_CHECKING:
    from .service import M2406Service

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeBiomarkerPanelRobustnessRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-06",
    title="Robustness shift/OOD challenge (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "biomarker panel or biological truth claim",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity or consent inference",
        "unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class RobustnessChallengeSubmission:
    """Opaque submission wrapper for strict request validation."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2406Request:
    """Opaque capability proving strict M24-06 request validation."""

    request: ChallengeBiomarkerPanelRobustnessRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-06 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M24-06 validation requires a robustness challenge submission")


class M2406Plugin(
    ModulePlugin[object, ValidatedM2406Request, BiomarkerPanelRobustnessChallengeResult]
):
    """Expose validate-then-challenge without a parse or authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2406Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2406Request:
        if not isinstance(request, RobustnessChallengeSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2406_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2406_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2406Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2406Request) -> BiomarkerPanelRobustnessChallengeResult:
        if not isinstance(request, ValidatedM2406Request):
            raise _InvalidExecutionTokenError
        return self._service.challenge(request.request)

    def replay(
        self, result: BiomarkerPanelRobustnessChallengeResult
    ) -> BiomarkerPanelRobustnessChallengeResult:
        return self._service.verify_replay(result)


__all__ = [
    "M2406Plugin",
    "RobustnessChallengeSubmission",
    "ValidatedM2406Request",
]
