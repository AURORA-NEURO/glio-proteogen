"""Strict parse-once plugin boundary for M09-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_03 import (
    M0903_MAX_CANONICAL_REQUEST_BYTES,
    EstimateComplexActivityBaselineRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import BuiltM0903Result

if TYPE_CHECKING:
    from .service import M0903Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(EstimateComplexActivityBaselineRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M09-03",
    title="mature complex-activity baseline estimator (provisional)",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or treatment recommendation",
        "identity or consent inference or unsupported-to-negative conversion",
        "protein-level subtype claims outside the complex-activity parent boundary",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0903Request:
    request: EstimateComplexActivityBaselineRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0903Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M09-03 execution requires a validated request token")


class M0903Plugin(ModulePlugin[object, ValidatedM0903Request, BuiltM0903Result]):
    """Expose M09-03 through a parse-once token-bound plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0903Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0903Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            strict_json_loads(serialized, max_bytes=M0903_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(serialized) if isinstance(serialized, bytearray) else serialized
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        typed = self._service.validate_request(candidate)
        token = ValidatedM0903Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0903Request) -> BuiltM0903Result:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError:
            snapshot = None
        if (
            type(request) is not ValidatedM0903Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0903Plugin", "ValidatedM0903Request"]
