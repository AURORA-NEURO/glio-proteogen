"""Capability-gated plugin boundary for M14-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m14_05 import (
    M1405_MAX_CANONICAL_REQUEST_BYTES,
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    ProteinSubtypeLongitudinalEvolutionResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m1405_authorization

if TYPE_CHECKING:
    from .service import M1405Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M14-05",
    title="Longitudinal protein-subtype evolution (provisional)",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "unfrozen biological state or change-point inference from opaque references",
        "KINOPHOS kinase ownership, generic all-omics fusion, or treatment recommendation",
        (
            "identity or consent inference, disagreement erasure, or "
            "unsupported-to-negative conversion"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1405Request:
    request: ModelProteinSubtypeLongitudinalEvolutionRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M14-05 execution requires a validated request token")


class M1405Plugin(
    ModulePlugin[object, ValidatedM1405Request, ProteinSubtypeLongitudinalEvolutionResult]
):
    """Grant one immutable bounded temporal replay capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M1405Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1405Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            strict_json_loads(serialized, max_bytes=M1405_MAX_CANONICAL_REQUEST_BYTES)
            typed = ModelProteinSubtypeLongitudinalEvolutionRequest.model_validate_json(serialized)
        else:
            preflight_m1405_authorization(request)
            typed = self._service.validate_request(request)
        return ValidatedM1405Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1405Request) -> ProteinSubtypeLongitudinalEvolutionResult:
        if type(request) is not ValidatedM1405Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeLongitudinalEvolutionResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1405Plugin", "ValidatedM1405Request"]
