"""Strict validate-then-run plugin boundary for M05-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m05_05 import (
    M0505_MAX_CANONICAL_REQUEST_BYTES,
    DetectPtmLocalizationArtifactsRequest,
    PtmLocalizationArtifactDetectionResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection.engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection.service import (
        M0505Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M05-05",
    title="PTM-localization artifact and contamination detector",
    version="1.0.0",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, sequences, accessions, abundance values, or external content",
        "identity, consent, PTM-localization, protein, proteoform, or subtype inference",
        "proteogenomic state, proteotype, subtype, or variant-peptide emission",
        "kinase-state inference, all-omics fusion, treatment advice, or clinical decisions",
        "upstream mutation, relabeling, missing-as-negative conversion, or model execution",
    ),
)


@dataclass(frozen=True, slots=True)
class M0505Submission:
    """Plugin submission wrapper retained for a stable module boundary."""

    request: object


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0505Request:
    request: DetectPtmLocalizationArtifactsRequest
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[ValidatedM0505Request, tuple[DetectPtmLocalizationArtifactsRequest, str]]
] = WeakKeyDictionary()


def _token_is_issued(token: ValidatedM0505Request) -> bool:
    snapshot = _ISSUED_TOKENS.get(token)
    return (
        snapshot is not None
        and snapshot[0] is token.request
        and snapshot[1] == canonical_request_digest(token.request)
    )


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-05 execution requires a validated request token")


class M0505Plugin(
    ModulePlugin[object, ValidatedM0505Request, PtmLocalizationArtifactDetectionResult]
):
    """Grant one immutable M05-05 execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0505Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0505Request:
        candidate = request.request if type(request) is M0505Submission else request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(serialized, max_bytes=M0505_MAX_CANONICAL_REQUEST_BYTES)
            typed = _validate_json_request(candidate, serialized)
        else:
            typed = self._service.validate_request(candidate)
        token = ValidatedM0505Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0505Request) -> PtmLocalizationArtifactDetectionResult:
        if (
            type(request) is not ValidatedM0505Request
            or request._seal is not _TOKEN_SEAL
            or not _token_is_issued(request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0505Plugin", "M0505Submission", "ValidatedM0505Request"]
