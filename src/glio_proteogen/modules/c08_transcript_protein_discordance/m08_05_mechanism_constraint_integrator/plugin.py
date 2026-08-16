"""Strict validate-then-run plugin boundary for provisional M08-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_05 import (
    M0805_MAX_CANONICAL_REQUEST_BYTES,
    IntegrateTranscriptProteinConstraintsRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import BuiltM0805Result

if TYPE_CHECKING:
    from .service import M0805Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateTranscriptProteinConstraintsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M08-05",
    title="transcript-protein mechanism and constraint integrator (provisional)",
    version="0.1.0-provisional",
    owner="ML engineering",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or treatment recommendation",
        "parent protein-subtype emission, identity inference, or consent inference",
        "unsupported-to-negative conversion or upstream evidence mutation",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0805Request:
    request: IntegrateTranscriptProteinConstraintsRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0805Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M08-05 execution requires a validated request token")


class M0805Plugin(
    ModulePlugin[
        object,
        ValidatedM0805Request,
        BuiltM0805Result,
    ]
):
    """Expose M08-05 through a parse-once, token-bound plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0805Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0805Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            strict_json_loads(
                serialized,
                max_bytes=M0805_MAX_CANONICAL_REQUEST_BYTES,
            )
            raw = bytes(serialized) if isinstance(serialized, bytearray) else serialized
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        typed = self._service.validate_request(candidate)
        token = ValidatedM0805Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0805Request) -> BuiltM0805Result:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0805Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0805Plugin", "ValidatedM0805Request"]
