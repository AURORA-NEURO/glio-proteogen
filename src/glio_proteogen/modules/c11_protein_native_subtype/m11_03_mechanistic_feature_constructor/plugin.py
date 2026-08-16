"""Strict parse-once plugin boundary for M11-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m11_03 import (
    M1103_MAX_CANONICAL_REQUEST_BYTES,
    ConstructVariantPeptideMechanisticFeaturesRequest,
    VariantPeptideMechanisticFeatureResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from .service import (
        M1103Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M11-03",
    title="Mechanistic feature constructor",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "KINOPHOS kinase-state inference",
        "generic all-omics fusion or direct treatment recommendation",
        "identity or consent inference, upstream relabeling, or opaque payload traversal",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1103Request:
    request: ConstructVariantPeptideMechanisticFeaturesRequest
    _seal: object


class _InvalidTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M11-03 execution requires a validated request token")


class M1103Plugin(
    ModulePlugin[object, ValidatedM1103Request, VariantPeptideMechanisticFeatureResult]
):
    __slots__ = ("_service",)

    def __init__(self, service: M1103Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1103Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized, max_bytes=M1103_MAX_CANONICAL_REQUEST_BYTES)
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = self._service.validate_request(request)
        return ValidatedM1103Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1103Request) -> VariantPeptideMechanisticFeatureResult:
        if type(request) is not ValidatedM1103Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidTokenError
        return self._service.execute(request.request)


__all__ = ["M1103Plugin", "ValidatedM1103Request"]
