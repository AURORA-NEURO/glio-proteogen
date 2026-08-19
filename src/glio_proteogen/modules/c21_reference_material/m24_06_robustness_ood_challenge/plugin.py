"""Strict plugin boundary for provisional M24-06 robustness challenges."""

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

_ADAPTER: Final = TypeAdapter(ChallengeBiomarkerPanelRobustnessRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-06",
    title="Robustness and OOD challenge surface (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "clinical or biological probability",
        "protein/proteoform/isoform or glioma inference",
        "treatment, kinase, identity or consent inference",
        "unsupported-to-negative conversion",
    ),
)


@dataclass(frozen=True, slots=True)
class RobustnessSubmission:
    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2406Request:
    request: ChallengeBiomarkerPanelRobustnessRequest


class M2406Plugin(
    ModulePlugin[object, ValidatedM2406Request, BiomarkerPanelRobustnessChallengeResult]
):
    __slots__ = ("_service",)

    def __init__(self, service: M2406Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2406Request:
        if not isinstance(request, RobustnessSubmission):
            raise TypeError("M24-06 validation requires a robustness submission")  # noqa: TRY003
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2406_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2406_authorization(decoded)
            candidate = _ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2406Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2406Request) -> BiomarkerPanelRobustnessChallengeResult:
        if not isinstance(request, ValidatedM2406Request):
            raise TypeError("M24-06 execution requires a validated request token")  # noqa: TRY003
        return self._service.evaluate(request.request)

    def replay(
        self, result: BiomarkerPanelRobustnessChallengeResult
    ) -> BiomarkerPanelRobustnessChallengeResult:
        return self._service.verify_replay(result)


__all__ = ["M2406Plugin", "RobustnessSubmission", "ValidatedM2406Request"]
