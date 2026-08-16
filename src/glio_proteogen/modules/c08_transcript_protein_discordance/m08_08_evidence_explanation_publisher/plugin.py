"""Strict parse-once plugin boundary for the provisional M08-08 publisher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_08 import (
    M0808_MAX_CANONICAL_REQUEST_BYTES,
    PublishTranscriptProteinEvidenceRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import BuiltM0808Result

if TYPE_CHECKING:
    from .service import M0808Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(PublishTranscriptProteinEvidenceRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M08-08",
    title="transcript-protein evidence and explanation publisher (provisional)",
    version="0.1.0-provisional",
    owner="Data engineering",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or treatment recommendation",
        "identity inference, consent inference, or upstream evidence mutation",
        "unsupported-to-negative conversion or parent protein-subtype emission",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0808Request:
    request: PublishTranscriptProteinEvidenceRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0808Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M08-08 execution requires a validated request token")


class M0808Plugin(ModulePlugin[object, ValidatedM0808Request, BuiltM0808Result]):
    """Expose M08-08 through a parse-once, token-bound plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0808Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0808Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            strict_json_loads(serialized, max_bytes=M0808_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(serialized) if isinstance(serialized, bytearray) else serialized
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        typed = self._service.validate_request(candidate)
        token = ValidatedM0808Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0808Request) -> BuiltM0808Result:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0808Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0808Plugin", "ValidatedM0808Request"]
