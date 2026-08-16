"""Strict validate-then-run plugin boundary for provisional M07-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_03 import (
    M0703_MAX_CANONICAL_REQUEST_BYTES,
    EstimateCopyNumberDosageBaselineRequest,
    EstimateCopyNumberDosageBaselineResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from .service import M0703Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(EstimateCopyNumberDosageBaselineRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M07-03",
    title="copy-number dosage mature baseline estimator (provisional)",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or treatment recommendations",
        "kinase activity, generic all-omics fusion, or parent proteotype emission",
        "unsupported-to-negative conversion or untyped missing values",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0703Request:
    request: EstimateCopyNumberDosageBaselineRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0703Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-03 execution requires a validated request token")


class M0703Plugin(
    ModulePlugin[
        object,
        ValidatedM0703Request,
        EstimateCopyNumberDosageBaselineResult,
    ]
):
    """Expose M07-03 through the common plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0703Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0703Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            parsed = strict_json_loads(
                serialized,
                max_bytes=M0703_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(candidate)
        token = ValidatedM0703Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0703Request) -> EstimateCopyNumberDosageBaselineResult:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0703Request
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
    ) -> EstimateCopyNumberDosageBaselineResult:
        """Verify a result through the same service boundary as execution."""

        return self._service.verify(result, replay=replay)


__all__ = ["M0703Plugin", "ValidatedM0703Request"]
