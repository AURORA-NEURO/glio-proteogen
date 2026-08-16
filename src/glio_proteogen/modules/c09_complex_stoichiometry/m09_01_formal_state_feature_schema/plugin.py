"""Sealed parse-once plugin boundary for M09-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m09_01 import (
    M0901_MAX_CANONICAL_REQUEST_BYTES,
    ValidateComplexActivityStateRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    BuiltM0901Result,
    _validate_json_request,
)

if TYPE_CHECKING:
    from .service import M0901Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M09-01",
    title="formal complex-activity state and feature schema (provisional)",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "kinase-state ownership, generic all-omics fusion, or direct treatment recommendation",
        "identity or consent inference, upstream mutation, or unsupported-to-negative conversion",
        "arbitrary expression execution or unbounded external-content traversal",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0901Request:
    request: ValidateComplexActivityStateRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0901Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M09-01 execution requires a validated request token")


class M0901Plugin(
    ModulePlugin[object, ValidatedM0901Request, BuiltM0901Result],
):
    """Expose M09-01 through a sealed validate-then-run ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0901Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0901Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized, max_bytes=M0901_MAX_CANONICAL_REQUEST_BYTES)
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = self._service.validate_request(request)
        token = ValidatedM0901Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0901Request) -> BuiltM0901Result:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM0901Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0901Plugin", "ValidatedM0901Request"]
