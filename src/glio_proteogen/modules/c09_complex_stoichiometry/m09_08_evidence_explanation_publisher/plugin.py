"""Strict parse-once plugin boundary for provisional M09-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_08 import (
    M0908_MAX_CANONICAL_REQUEST_BYTES,
    PublishComplexActivityEvidenceRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import BuiltM0908Result

if TYPE_CHECKING:
    from .service import M0908Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(PublishComplexActivityEvidenceRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M09-08",
    title="complex activity evidence and explanation publisher (provisional)",
    version="0.1.0-provisional",
    owner="Platform engineering",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or direct treatment recommendation",
        "identity or consent inference, upstream evidence mutation, or disagreement erasure",
        "unsupported or missing evidence converted into a negative finding",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0908Request:
    request: PublishComplexActivityEvidenceRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0908Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class M0908Plugin(ModulePlugin[object, ValidatedM0908Request, BuiltM0908Result]):
    """Expose M09-08 through a parse-once, token-bound plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0908Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0908Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            strict_json_loads(serialized, max_bytes=M0908_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(serialized) if isinstance(serialized, bytearray) else serialized
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        typed = self._service.validate_request(candidate)
        token = ValidatedM0908Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0908Request) -> BuiltM0908Result:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0908Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise TypeError
        return self._service.execute(request.request)


__all__ = ["M0908Plugin", "ValidatedM0908Request"]
