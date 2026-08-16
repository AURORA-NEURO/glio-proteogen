"""Strict parse-once M12-01 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_01 import (
    M1201_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelHypothesisRegistryResult,
    RegisterBiomarkerPanelHypothesesRequest,
)
from glio_proteogen.contracts.m12_01.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import _prepare

if TYPE_CHECKING:
    from .service import M1201Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(RegisterBiomarkerPanelHypothesesRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M12-01",
    title="biological hypothesis registry (provisional)",
    version="0.1.0-provisional",
    owner="ML engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, treatment recommendation",
        "identity/consent inference or unsupported-to-negative conversion",
        "upstream mutation, relabeling, or disagreement erasure",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1201Request:
    request: RegisterBiomarkerPanelHypothesesRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM1201Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M12-01 execution requires a validated request token")


class M1201Plugin(
    ModulePlugin[object, ValidatedM1201Request, BiomarkerPanelHypothesisRegistryResult]
):
    """Expose M12-01 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1201Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1201Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(serialized, max_bytes=M1201_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(_prepare(request))
        token = ValidatedM1201Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1201Request) -> BiomarkerPanelHypothesisRegistryResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1201Request
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
    ) -> BiomarkerPanelHypothesisRegistryResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1201Plugin", "ValidatedM1201Request"]
