"""Strict parse-once plugin boundary for provisional M16-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_07 import (
    M1607_MAX_CANONICAL_REQUEST_BYTES,
    ExportProteinRnaDiscordanceDownstreamContractRequest,
    ProteinRnaDiscordanceDownstreamExportResult,
)
from glio_proteogen.contracts.m16_07.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_export_authorization

if TYPE_CHECKING:
    from .service import M1607Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(ExportProteinRnaDiscordanceDownstreamContractRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M16-07",
    title="downstream typed export (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or direct treatment recommendation",
        "identity, consent, or clinical decision inference",
        "unsupported-to-negative conversion, mutation, relabeling, or erasure",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1607Request:
    """Opaque capability proving strict M16-07 request acceptance."""

    request: ExportProteinRnaDiscordanceDownstreamContractRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM1607Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M16-07 execution requires a validated request token")


class M1607Plugin(
    ModulePlugin[
        object,
        ValidatedM1607Request,
        ProteinRnaDiscordanceDownstreamExportResult,
    ]
):
    """Expose M16-07 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1607Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1607Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(serialized, max_bytes=M1607_MAX_CANONICAL_REQUEST_BYTES)
            preflight_export_authorization(parsed)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(request)
            preflight_export_authorization(typed)
        token = ValidatedM1607Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1607Request) -> ProteinRnaDiscordanceDownstreamExportResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1607Request
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
    ) -> ProteinRnaDiscordanceDownstreamExportResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1607Plugin", "ValidatedM1607Request"]
