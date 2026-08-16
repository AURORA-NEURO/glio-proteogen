"""Strict parse-once M12-04 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_04 import (
    M1204_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelMechanismInferenceResult,
    InferBiomarkerPanelMechanismRequest,
)
from glio_proteogen.contracts.m12_04.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_mechanism_authorization

if TYPE_CHECKING:
    from .service import M1204Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(InferBiomarkerPanelMechanismRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M12-04",
    title="network/state/mechanism inference (provisional)",
    version="0.1.0-provisional",
    owner="Data engineering",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or direct treatment recommendation",
        "identity/consent inference or unsupported-to-negative conversion",
        "upstream mutation, relabeling, disagreement erasure, or parent output emission",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1204Request:
    """Opaque capability proving strict M12-04 request acceptance."""

    request: InferBiomarkerPanelMechanismRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM1204Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M12-04 execution requires a validated request token")


class M1204Plugin(
    ModulePlugin[object, ValidatedM1204Request, BiomarkerPanelMechanismInferenceResult]
):
    """Expose M12-04 through validate-then-run token semantics."""

    __slots__ = ("_service",)

    def __init__(self, service: M1204Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1204Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(serialized, max_bytes=M1204_MAX_CANONICAL_REQUEST_BYTES)
            preflight_mechanism_authorization(parsed)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(request)
        token = ValidatedM1204Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1204Request) -> BiomarkerPanelMechanismInferenceResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM1204Request
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
    ) -> BiomarkerPanelMechanismInferenceResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1204Plugin", "ValidatedM1204Request"]
