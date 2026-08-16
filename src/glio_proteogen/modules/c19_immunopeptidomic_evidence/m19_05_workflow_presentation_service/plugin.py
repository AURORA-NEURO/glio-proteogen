"""Strict parse-once plugin boundary for M19-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_05 import (
    M1905_MAX_CANONICAL_REQUEST_BYTES,
    PresentProteotypeHumanReviewWorkspaceRequest,
    ProteotypeHumanReviewWorkspaceResult,
)
from glio_proteogen.contracts.m19_05.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m1905_authorization

if TYPE_CHECKING:
    from .service import M1905Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(PresentProteotypeHumanReviewWorkspaceRequest)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1905Request:
    """Opaque token proving strict request validation and authorization."""

    request: PresentProteotypeHumanReviewWorkspaceRequest
    _seal: object


_ISSUED_TOKENS: Final = WeakKeyDictionary[ValidatedM1905Request, tuple[object, str]]()


class InvalidM1905ExecutionTokenError(TypeError):
    """Execution requires an unmodified token issued by ``validate``."""

    def __init__(self) -> None:
        super().__init__("M19-05 execution requires a validated request token")


class M1905Plugin(
    ModulePlugin[object, ValidatedM1905Request, ProteotypeHumanReviewWorkspaceResult]
):
    """Expose M19-05 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1905Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return self._service.descriptor()

    def validate(self, request: object) -> ValidatedM1905Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(
                serialized,
                max_bytes=M1905_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
            preflight_m1905_authorization(typed)
        else:
            typed = self._service.validate_request(request)
        token = ValidatedM1905Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1905Request) -> ProteotypeHumanReviewWorkspaceResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise InvalidM1905ExecutionTokenError from error
        if (
            type(request) is not ValidatedM1905Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise InvalidM1905ExecutionTokenError
        return self._service._engine.present(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeHumanReviewWorkspaceResult:
        return self._service.verify(result, replay=replay)


__all__ = [
    "InvalidM1905ExecutionTokenError",
    "M1905Plugin",
    "ValidatedM1905Request",
]
