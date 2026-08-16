"""Strict parse-once plugin boundary for provisional M15-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_01 import (
    M1501_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityHypothesisRegistryResult,
    RegisterComplexActivityHypothesesRequest,
)
from glio_proteogen.contracts.m15_01.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_hypothesis_authorization

if TYPE_CHECKING:
    from .service import M1501Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(RegisterComplexActivityHypothesesRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M15-01",
    title="biological hypothesis registry (provisional)",
    version="0.1.0-provisional",
    owner="Data engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or direct treatment recommendation",
        "identity, consent, or clinical decision inference",
        "unsupported-to-negative conversion, mutation, relabeling, or erasure",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1501Request:
    """Opaque capability proving strict M15-01 request acceptance."""

    request: RegisterComplexActivityHypothesesRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM1501Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-01 execution requires a validated request token")


class M1501Plugin(
    ModulePlugin[
        object,
        ValidatedM1501Request,
        ComplexActivityHypothesisRegistryResult,
    ]
):
    """Expose M15-01 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1501Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1501Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(serialized, max_bytes=M1501_MAX_CANONICAL_REQUEST_BYTES)
            preflight_hypothesis_authorization(parsed)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(request)
            preflight_hypothesis_authorization(typed)
        token = ValidatedM1501Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1501Request) -> ComplexActivityHypothesisRegistryResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1501Request
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
    ) -> ComplexActivityHypothesisRegistryResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1501Plugin", "ValidatedM1501Request"]
