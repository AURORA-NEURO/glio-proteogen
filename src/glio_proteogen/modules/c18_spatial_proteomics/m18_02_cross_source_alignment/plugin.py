"""Strict parse-once plugin boundary for provisional M18-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_02 import (
    M1802_MAX_CANONICAL_REQUEST_BYTES,
    AlignBiomarkerPanelSourcesRequest,
    BiomarkerPanelAlignmentResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import _prepare

if TYPE_CHECKING:
    from .service import M1802Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(AlignBiomarkerPanelSourcesRequest)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1802Request:
    request: AlignBiomarkerPanelSourcesRequest
    _seal: object


_ISSUED_TOKENS: Final = WeakKeyDictionary[ValidatedM1802Request, tuple[object, str]]()


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M18-02 execution requires a validated request token")


class M1802Plugin(ModulePlugin[object, ValidatedM1802Request, BiomarkerPanelAlignmentResult]):
    """Expose M18-02 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1802Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return self._service.descriptor()

    def validate(self, request: object) -> ValidatedM1802Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(serialized, max_bytes=M1802_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(_prepare(request))
        token = ValidatedM1802Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1802Request) -> BiomarkerPanelAlignmentResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1802Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._engine.infer(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelAlignmentResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1802Plugin", "ValidatedM1802Request"]
