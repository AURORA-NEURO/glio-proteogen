"""Strict validate-then-run plugin boundary for provisional M08-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_06 import (
    M0806_MAX_CANONICAL_REQUEST_BYTES,
    DecomposeTranscriptProteinUncertaintyRequest,
    TranscriptProteinUncertaintyDecompositionResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from .service import M0806Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeTranscriptProteinUncertaintyRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M08-06",
    title="transcript-protein uncertainty decomposition (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or treatment recommendations",
        "kinase state, generic all-omics fusion, or parent protein-subtype emission",
        "unsupported-to-negative conversion or hidden uncertainty residuals",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0806Request:
    request: DecomposeTranscriptProteinUncertaintyRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0806Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M08-06 execution requires a validated request token")


class M0806Plugin(
    ModulePlugin[
        object,
        ValidatedM0806Request,
        TranscriptProteinUncertaintyDecompositionResult,
    ]
):
    """Expose M08-06 through the common plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0806Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0806Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0806_MAX_CANONICAL_REQUEST_BYTES,
            )
        if isinstance(candidate, dict):
            candidate = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
        typed = self._service.validate_request(candidate)
        token = ValidatedM0806Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(
        self, request: ValidatedM0806Request
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0806Request
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
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M0806Plugin", "ValidatedM0806Request"]
