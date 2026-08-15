"""Strict parse-once plugin boundary for M10-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m10_08 import (
    M1008_MAX_CANONICAL_REQUEST_BYTES,
    ProteinRnaEvidencePublicationResult,
    PublishProteinRnaEvidenceRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    _validate_authorized_request,
)

if TYPE_CHECKING:
    from .service import (
        M1008EvidencePublisherService,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M10-08",
    title="Evidence and explanation publisher",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or direct treatment recommendation",
        "identity or consent inference, raw external payload traversal, or upstream mutation",
        "unsupported or missing evidence represented as a negative finding",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1008Request:
    """Opaque capability proving strict M10-08 request acceptance."""

    request: PublishProteinRnaEvidenceRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-08 execution requires a validated request token")


class M1008EvidencePublisherPlugin(
    ModulePlugin[object, ValidatedM1008Request, ProteinRnaEvidencePublicationResult]
):
    """Validate once, then grant one immutable execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M1008EvidencePublisherService) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1008Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(
                serialized,
                max_bytes=M1008_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _validate_authorized_request(decoded)
        else:
            typed = self._service.validate_request(request)
        return ValidatedM1008Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1008Request) -> ProteinRnaEvidencePublicationResult:
        if type(request) is not ValidatedM1008Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M1008EvidencePublisherPlugin", "ValidatedM1008Request"]
