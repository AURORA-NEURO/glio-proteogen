"""Strict validate-then-run plugin boundary for provisional M08-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m08_07 import (
    M0807_MAX_CANONICAL_REQUEST_BYTES,
    CalibrateProteinSubtypeSelectivePredictionRequest,
    ProteinSubtypeSelectivePredictionResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from .service import M0807Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M08-07",
    title="protein-subtype calibration and selective prediction (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or treatment recommendations",
        "kinase activity, generic all-omics fusion, or parent protein-subtype emission",
        "unsupported-to-negative conversion or hidden OOD acceptance",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0807Request:
    request: CalibrateProteinSubtypeSelectivePredictionRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0807Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M08-07 execution requires a validated request token")


class M0807Plugin(
    ModulePlugin[
        object,
        ValidatedM0807Request,
        ProteinSubtypeSelectivePredictionResult,
    ]
):
    """Expose M08-07 through the common plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0807Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0807Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0807_MAX_CANONICAL_REQUEST_BYTES,
            )
        typed = self._service.validate_request(candidate)
        token = ValidatedM0807Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0807Request) -> ProteinSubtypeSelectivePredictionResult:
        if type(request) is not ValidatedM0807Request:
            raise _InvalidExecutionTokenError
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0807Plugin", "ValidatedM0807Request"]
