"""Strict validate-then-run plugin boundary for provisional M08-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m08_04 import (
    M0804_MAX_CANONICAL_REQUEST_BYTES,
    EstimateTranscriptProteinProbabilisticRequest,
    EstimateTranscriptProteinProbabilisticResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import _validate_json_request

if TYPE_CHECKING:
    from .service import M0804Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M08-04",
    title="transcript-protein probabilistic estimator (provisional)",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or treatment recommendations",
        "kinase activity, generic all-omics fusion, or parent protein-subtype emission",
        "unsupported-to-negative conversion or untyped missing values",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0804Request:
    request: EstimateTranscriptProteinProbabilisticRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0804Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M08-04 execution requires a validated request token")


class M0804Plugin(
    ModulePlugin[
        object,
        ValidatedM0804Request,
        EstimateTranscriptProteinProbabilisticResult,
    ]
):
    """Expose M08-04 through the common plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0804Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0804Request:
        candidate = request
        serialized: bytes | bytearray | str | None = None
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0804_MAX_CANONICAL_REQUEST_BYTES,
            )
        if serialized is None:
            typed = self._service.validate_request(candidate)
        else:
            typed = _validate_json_request(candidate, serialized)
        token = ValidatedM0804Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0804Request) -> EstimateTranscriptProteinProbabilisticResult:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0804Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0804Plugin", "ValidatedM0804Request"]
