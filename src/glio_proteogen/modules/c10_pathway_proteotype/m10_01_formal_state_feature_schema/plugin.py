"""Strict parse-once plugin boundary for provisional M10-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_01 import (
    M1001_MAX_CANONICAL_REQUEST_BYTES,
    ValidateProteinRnaDiscordanceStateRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import BuiltM1001Result

if TYPE_CHECKING:
    from .service import M1001Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(ValidateProteinRnaDiscordanceStateRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M10-01",
    title="formal state and feature schema (provisional)",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or treatment recommendation",
        "parent protein-RNA discordance emission, identity inference, or consent inference",
        "unsupported-to-negative conversion or upstream evidence mutation",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1001Request:
    request: ValidateProteinRnaDiscordanceStateRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM1001Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-01 execution requires a validated request token")


class M1001Plugin(ModulePlugin[object, ValidatedM1001Request, BuiltM1001Result]):
    """Expose M10-01 through parse-once, digest-bound execution tokens."""

    __slots__ = ("_service",)

    def __init__(self, service: M1001Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1001Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            strict_json_loads(serialized, max_bytes=M1001_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(serialized) if isinstance(serialized, bytearray) else serialized
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        typed = self._service.validate_request(candidate)
        token = ValidatedM1001Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1001Request) -> BuiltM1001Result:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM1001Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M1001Plugin", "ValidatedM1001Request"]
