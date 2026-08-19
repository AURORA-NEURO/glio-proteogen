"""Strict parse-once plugin boundary for provisional M18-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_05 import (
    M1805_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelReviewWorkspaceResult,
    PresentBiomarkerPanelReviewWorkspaceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import _prepare

if TYPE_CHECKING:
    from .service import M1805Service

_REQUEST_ADAPTER: Final = TypeAdapter(PresentBiomarkerPanelReviewWorkspaceRequest)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1805Request:
    request: PresentBiomarkerPanelReviewWorkspaceRequest
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1805Request,
        tuple[object, PresentBiomarkerPanelReviewWorkspaceRequest, bytes],
    ]
] = WeakKeyDictionary()


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M18-05 execution requires a validated request token")


class M1805Plugin(ModulePlugin[object, ValidatedM1805Request, BiomarkerPanelReviewWorkspaceResult]):
    """Expose M18-05 through validate-then-run token semantics."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M1805Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return self._service.descriptor()

    def validate(self, request: object) -> ValidatedM1805Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(serialized, max_bytes=M1805_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(_prepare(request))
        token = ValidatedM1805Request(request=typed, _seal=self._seal)
        _ISSUED_TOKENS[token] = (self._seal, typed, canonical_json_bytes(typed))
        return token

    def run(self, request: ValidatedM1805Request) -> BiomarkerPanelReviewWorkspaceResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1805Request
            or request._seal is not self._seal
            or snapshot is None
            or snapshot[0] is not self._seal
            or snapshot[1] is not request.request
        ):
            raise _InvalidExecutionTokenError
        try:
            current_bytes = canonical_json_bytes(request.request)
        except (TypeError, ValueError) as error:
            raise _InvalidExecutionTokenError from error
        if current_bytes != snapshot[2]:
            raise _InvalidExecutionTokenError
        return self._service._engine.infer(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelReviewWorkspaceResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1805Plugin", "ValidatedM1805Request"]
