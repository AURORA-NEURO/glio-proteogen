"""Strict validate-then-run plugin boundary for M13-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m13_02 import (
    M1302_MAX_CANONICAL_REQUEST_BYTES,
    ProteotypeContextStratificationResult,
    StratifyProteotypeContextRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    DESCRIPTOR,
)

if TYPE_CHECKING:
    from .service import (
        M1302Service,
    )

@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1302Request:
    request: StratifyProteotypeContextRequest
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1302Request,
        tuple[object, StratifyProteotypeContextRequest, bytes],
    ]
] = WeakKeyDictionary()


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M13-02 execution requires a validated request token")


class M1302Plugin(
    ModulePlugin[object, ValidatedM1302Request, ProteotypeContextStratificationResult]
):
    """Grant one immutable capability bound to the strict request."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M1302Service) -> None:
        self._service = service
        self._seal = object()

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
        token = ValidatedM1302Request(request=typed, _seal=self._seal)
        _ISSUED_TOKENS[token] = (self._seal, typed, canonical_json_bytes(typed))
        return token

    def run(self, request: ValidatedM1302Request) -> ProteotypeContextStratificationResult:
        if type(request) is not ValidatedM1302Request:
            raise _InvalidExecutionTokenError
        snapshot = _ISSUED_TOKENS.get(request)
        if snapshot is None or snapshot[0] is not self._seal or request._seal is not self._seal:
            raise _InvalidExecutionTokenError
        if snapshot[1] is not request.request:
            raise _InvalidExecutionTokenError
        try:
            current_bytes = canonical_json_bytes(request.request)
        except (TypeError, ValueError) as error:
            raise _InvalidExecutionTokenError from error
        if current_bytes != snapshot[2]:
            raise _InvalidExecutionTokenError
        return self._service.execute(snapshot[1])


__all__ = ["M1302Plugin", "ValidatedM1302Request"]
