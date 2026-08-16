"""Strict parse-once plugin boundary for provisional M17-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_05 import (
    M1705_MAX_CANONICAL_REQUEST_BYTES,
    PresentVariantPeptideHumanReviewWorkspaceRequest,
    VariantPeptideHumanReviewWorkspaceResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import _prepare

if TYPE_CHECKING:
    from .service import M1705Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(PresentVariantPeptideHumanReviewWorkspaceRequest)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1705Request:
    request: PresentVariantPeptideHumanReviewWorkspaceRequest
    _seal: object


_ISSUED_TOKENS: Final = WeakKeyDictionary[ValidatedM1705Request, tuple[object, str]]()


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M17-05 execution requires a validated request token")


class M1705Plugin(
    ModulePlugin[object, ValidatedM1705Request, VariantPeptideHumanReviewWorkspaceResult]
):
    """Expose M17-05 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1705Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return self._service.descriptor()

    def validate(self, request: object) -> ValidatedM1705Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(serialized, max_bytes=M1705_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(_prepare(request))
        token = ValidatedM1705Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1705Request) -> VariantPeptideHumanReviewWorkspaceResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1705Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideHumanReviewWorkspaceResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1705Plugin", "ValidatedM1705Request"]
