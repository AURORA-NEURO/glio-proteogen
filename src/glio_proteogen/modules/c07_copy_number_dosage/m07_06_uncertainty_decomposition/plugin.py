"""Strict validate-then-run plugin boundary for provisional M07-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m07_06 import (
    M0706_MAX_CANONICAL_REQUEST_BYTES,
    CopyNumberDosageUncertaintyDecompositionResult,
    DecomposeCopyNumberDosageUncertaintyRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from .service import M0706Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M07-06",
    title="copy-number dosage uncertainty decomposition (provisional)",
    version="0.1.0-provisional",
    owner="ML engineering",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or treatment recommendations",
        "kinase activity, generic all-omics fusion, or parent proteotype emission",
        "unsupported-to-negative conversion or hidden uncertainty residuals",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0706Request:
    request: DecomposeCopyNumberDosageUncertaintyRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0706Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-06 execution requires a validated request token")


class M0706Plugin(
    ModulePlugin[
        object,
        ValidatedM0706Request,
        CopyNumberDosageUncertaintyDecompositionResult,
    ]
):
    """Expose M07-06 through the common plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0706Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0706Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0706_MAX_CANONICAL_REQUEST_BYTES,
            )
        typed = self._service.validate_request(candidate)
        token = ValidatedM0706Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0706Request) -> CopyNumberDosageUncertaintyDecompositionResult:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0706Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0706Plugin", "ValidatedM0706Request"]
