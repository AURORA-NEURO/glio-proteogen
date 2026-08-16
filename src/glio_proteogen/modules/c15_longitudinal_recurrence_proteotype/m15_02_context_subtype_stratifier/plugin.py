"""Capability-gated plugin boundary for M15-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m15_02 import (
    M1502_MAX_CANONICAL_REQUEST_BYTES,
    LongitudinalRecurrenceContextStratificationResult,
    StratifyContextAndSubtypeRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m1502_authorization

if TYPE_CHECKING:
    from .service import M1502Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M15-02",
    title="Context and subtype stratifier (provisional)",
    version="0.1.0-provisional",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "identity, subtype, or biological inference from opaque references",
        "KINOPHOS kinase state, generic all-omics fusion, or treatment recommendation",
        "disagreement erasure, consent inference, or unsupported-to-negative conversion",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1502Request:
    request: StratifyContextAndSubtypeRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-02 execution requires a validated request token")


class M1502Plugin(
    ModulePlugin[object, ValidatedM1502Request, LongitudinalRecurrenceContextStratificationResult]
):
    """Grant one immutable bounded context-replay capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M1502Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1502Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            strict_json_loads(serialized, max_bytes=M1502_MAX_CANONICAL_REQUEST_BYTES)
            typed = StratifyContextAndSubtypeRequest.model_validate_json(serialized, strict=True)
            preflight_m1502_authorization(typed)
        else:
            preflight_m1502_authorization(request)
            typed = self._service.validate_request(request)
        return ValidatedM1502Request(request=typed, _seal=_TOKEN_SEAL)

    def run(
        self, request: ValidatedM1502Request
    ) -> LongitudinalRecurrenceContextStratificationResult:
        if type(request) is not ValidatedM1502Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> LongitudinalRecurrenceContextStratificationResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1502Plugin", "ValidatedM1502Request"]
