"""Strict parse-once plugin boundary for provisional M17-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_03 import (
    M1703_MAX_CANONICAL_REQUEST_BYTES,
    FuseVariantPeptideEvidenceRequest,
    VariantPeptideIntegratedEvidenceResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import _prepare

if TYPE_CHECKING:
    from .service import M1703Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(FuseVariantPeptideEvidenceRequest)
_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM1703Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1703Request:
    request: FuseVariantPeptideEvidenceRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M17-03 execution requires a validated request token")


class M1703Plugin(
    ModulePlugin[object, ValidatedM1703Request, VariantPeptideIntegratedEvidenceResult]
):
    """Expose M17-03 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1703Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return self._service.descriptor()

    def validate(self, request: object) -> ValidatedM1703Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(serialized, max_bytes=M1703_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(_prepare(request))
        token = ValidatedM1703Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1703Request) -> VariantPeptideIntegratedEvidenceResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1703Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> VariantPeptideIntegratedEvidenceResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1703Plugin", "ValidatedM1703Request"]
