"""Capability-gated plugin boundary for M15-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m15_05 import (
    M1505_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityLongitudinalEvolutionResult,
    ModelComplexActivityLongitudinalEvolutionRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m1505_authorization

if TYPE_CHECKING:
    from .service import M1505Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M15-05",
    title="Longitudinal and evolutionary model (provisional)",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "unfrozen biological state or change-point inference from opaque references",
        "KINOPHOS kinase state, generic all-omics fusion, or treatment recommendation",
        (
            "identity or consent inference, disagreement erasure, or "
            "unsupported-to-negative conversion"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1505Request:
    request: ModelComplexActivityLongitudinalEvolutionRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-05 execution requires a validated request token")


class M1505Plugin(
    ModulePlugin[
        object,
        ValidatedM1505Request,
        ComplexActivityLongitudinalEvolutionResult,
    ]
):
    """Grant one immutable bounded temporal replay capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M1505Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1505Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            strict_json_loads(serialized, max_bytes=M1505_MAX_CANONICAL_REQUEST_BYTES)
            typed = ModelComplexActivityLongitudinalEvolutionRequest.model_validate_json(
                serialized,
                strict=True,
            )
            preflight_m1505_authorization(typed)
        else:
            preflight_m1505_authorization(request)
            typed = self._service.validate_request(request)
        return ValidatedM1505Request(request=typed, _seal=_TOKEN_SEAL)

    def run(
        self,
        request: ValidatedM1505Request,
    ) -> ComplexActivityLongitudinalEvolutionResult:
        if type(request) is not ValidatedM1505Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityLongitudinalEvolutionResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1505Plugin", "ValidatedM1505Request"]
