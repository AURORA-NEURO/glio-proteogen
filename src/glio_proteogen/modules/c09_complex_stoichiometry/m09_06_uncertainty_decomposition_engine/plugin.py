"""Sealed parse-once plugin boundary for provisional M09-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_06 import (
    M0906_MAX_CANONICAL_REQUEST_BYTES,
    DecomposeComplexActivityUncertaintyRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import BuiltM0906Result, _validate_json_request

if TYPE_CHECKING:
    from .service import M0906Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeComplexActivityUncertaintyRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M09-06",
    title="complex-activity uncertainty decomposition engine (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or direct treatment recommendation",
        "parent complex-activity emission, identity inference, or consent inference",
        "unsupported-to-negative conversion, upstream mutation, or external-content traversal",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0906Request:
    request: DecomposeComplexActivityUncertaintyRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0906Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M09-06 execution requires a validated request token")


class M0906Plugin(ModulePlugin[object, ValidatedM0906Request, BuiltM0906Result]):
    """Expose M09-06 through a sealed validate-then-run ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0906Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0906Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized, max_bytes=M0906_MAX_CANONICAL_REQUEST_BYTES)
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = self._service.validate_request(request)
        token = ValidatedM0906Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0906Request) -> BuiltM0906Result:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM0906Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0906Plugin", "ValidatedM0906Request"]
