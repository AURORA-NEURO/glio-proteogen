"""Strict parse-once plugin boundary for M13-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m13_07 import (
    M1307_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateProteotypePlausibilityRequest,
    ProteotypePlausibilityAdjudicationResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from .service import (
        M1307Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M13-07",
    title="Variant-peptide plausibility and negative-control adjudicator",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or treatment recommendation",
        "identity or consent inference, upstream mutation, or evidence relabeling",
        "unsupported or missing evidence converted into a negative finding",
        "raw payload traversal, external authority authentication, or parent emission",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1307Request:
    """Opaque capability proving strict M13-07 request acceptance."""

    request: AdjudicateProteotypePlausibilityRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M13-07 execution requires a validated request token")


class M1307Plugin(
    ModulePlugin[object, ValidatedM1307Request, ProteotypePlausibilityAdjudicationResult]
):
    """Grant one immutable capability for safe execution."""

    __slots__ = ("_service",)

    def __init__(self, service: M1307Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1307Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized, max_bytes=M1307_MAX_CANONICAL_REQUEST_BYTES)
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = self._service.validate_request(request)
        return ValidatedM1307Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1307Request) -> ProteotypePlausibilityAdjudicationResult:
        if type(request) is not ValidatedM1307Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M1307Plugin", "ValidatedM1307Request"]


