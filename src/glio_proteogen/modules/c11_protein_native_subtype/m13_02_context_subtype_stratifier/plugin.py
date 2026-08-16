"""Strict validate-then-run plugin boundary for M13-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m13_02 import (
    M1302_MAX_CANONICAL_REQUEST_BYTES,
    ProteotypeContextStratificationResult,
    StratifyProteotypeContextRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    DESCRIPTOR,
)

if TYPE_CHECKING:
    from .service import (
        M1302Service,
    )

_TOKEN_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class ValidatedM1302Request:
    request: StratifyProteotypeContextRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M13-02 execution requires a validated request token")


class M1302Plugin(
    ModulePlugin[object, ValidatedM1302Request, ProteotypeContextStratificationResult]
):
    """Grant one immutable capability bound to the strict request."""

    __slots__ = ("_service",)

    def __init__(self, service: M1302Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1302Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            # Decode once here for duplicate-key and size enforcement; validation
            # repeats no JSON parse and receives the decoded object via service.
            decoded = strict_json_loads(serialized, max_bytes=M1302_MAX_CANONICAL_REQUEST_BYTES)
            typed = self._service.validate_request(decoded)
        else:
            typed = self._service.validate_request(request)
        return ValidatedM1302Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1302Request) -> ProteotypeContextStratificationResult:
        if type(request) is not ValidatedM1302Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M1302Plugin", "ValidatedM1302Request"]
