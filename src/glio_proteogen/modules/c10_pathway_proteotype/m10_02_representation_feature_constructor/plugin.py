"""Strict parse-once plugin boundary for M10-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m10_02 import (
    M1002_MAX_CANONICAL_REQUEST_BYTES,
    ConstructProteinRnaRepresentationRequest,
    ProteinRnaRepresentationResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    validate_json_request,
)

if TYPE_CHECKING:
    from .service import (
        M1002Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M10-02",
    title="Pathway/proteotype representation and feature constructor",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "kinase activity or kinase-state ownership",
        "generic all-omics fusion, raw payload traversal, or direct treatment recommendation",
        "protein-RNA discordance parent output or protein-level subtype claim",
        "identity, consent, provenance, or upstream-support inference",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1002Request:
    """Opaque capability proving one strict request was validated."""

    request: ConstructProteinRnaRepresentationRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-02 execution requires a validated request token")


class M1002Plugin(ModulePlugin[object, ValidatedM1002Request, ProteinRnaRepresentationResult]):
    """Grant execution only to the exact token returned by ``validate``."""

    __slots__ = ("_service",)

    def __init__(self, service: M1002Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1002Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized, max_bytes=M1002_MAX_CANONICAL_REQUEST_BYTES)
            typed = validate_json_request(decoded, serialized)
        else:
            typed = self._service.validate_request(request)
        return ValidatedM1002Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1002Request) -> ProteinRnaRepresentationResult:
        if type(request) is not ValidatedM1002Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M1002Plugin", "ValidatedM1002Request"]
