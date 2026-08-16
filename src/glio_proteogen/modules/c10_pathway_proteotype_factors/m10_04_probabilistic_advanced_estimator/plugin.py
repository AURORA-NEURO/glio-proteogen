"""Strict parse-once plugin boundary for provisional M10-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_04 import (
    M1004_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinRnaDiscordanceProbabilisticRequest,
    ProteinRnaDiscordanceProbabilisticResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import _prepare

if TYPE_CHECKING:
    from .service import M1004Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinRnaDiscordanceProbabilisticRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M10-04",
    title="probabilistic or advanced estimator (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "parent protein-RNA discordance emission, kinase activity, generic all-omics fusion",
        "treatment recommendations or unsupported-to-negative conversion",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
        "unattributed posterior claims or traversal of opaque source payloads",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1004Request:
    request: EstimateProteinRnaDiscordanceProbabilisticRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM1004Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-04 execution requires a validated request token")


class M1004Plugin(
    ModulePlugin[object, ValidatedM1004Request, ProteinRnaDiscordanceProbabilisticResult]
):
    """Expose M10-04 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1004Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1004Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            parsed = strict_json_loads(serialized, max_bytes=M1004_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(_prepare(candidate))
        token = ValidatedM1004Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1004Request) -> ProteinRnaDiscordanceProbabilisticResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1004Request
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
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1004Plugin", "ValidatedM1004Request"]
