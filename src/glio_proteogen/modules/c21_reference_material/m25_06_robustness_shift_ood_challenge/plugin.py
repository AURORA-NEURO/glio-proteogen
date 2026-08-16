"""Strict parse-once plugin boundary for provisional M25-06."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_06 import (
    M2506_MAX_CANONICAL_REQUEST_BYTES,
    ChallengeProteotypeRobustnessRequest,
    ProteotypeRobustnessChallengeResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2506_authorization

if TYPE_CHECKING:
    from .service import M2506Service

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeProteotypeRobustnessRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M25-06",
    title="Robustness, shift and OOD challenge engine (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "proteotype or biological estimate",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, disagreement erasure, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class ChallengeSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2506Request:
    """Opaque capability proving strict M25-06 request validation."""

    request: ChallengeProteotypeRobustnessRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-06 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-06 validation requires a challenge submission")


class M2506Plugin(ModulePlugin[object, ValidatedM2506Request, ProteotypeRobustnessChallengeResult]):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2506Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2506Request:
        if not isinstance(request, ChallengeSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2506_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2506_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(candidate, Mapping):
            preflight_m2506_authorization(candidate)
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
        return ValidatedM2506Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM2506Request,
    ) -> ProteotypeRobustnessChallengeResult:
        if not isinstance(request, ValidatedM2506Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def replay(
        self,
        result: ProteotypeRobustnessChallengeResult,
    ) -> ProteotypeRobustnessChallengeResult:
        return self._service.verify_replay(result)


__all__ = ["ChallengeSubmission", "M2506Plugin", "ValidatedM2506Request"]
