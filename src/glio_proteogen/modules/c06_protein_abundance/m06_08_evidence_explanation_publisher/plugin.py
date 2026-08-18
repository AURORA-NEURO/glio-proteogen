"""Strict validate-then-run plugin boundary for provisional M06-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_08 import (
    M0608_MAX_CANONICAL_REQUEST_BYTES,
    ProteinAbundanceEvidencePublicationResult,
    PublishProteinAbundanceEvidenceRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import (
    _prepare,
)

if TYPE_CHECKING:
    from .service import M0608Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(PublishProteinAbundanceEvidenceRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M06-08",
    title="evidence and explanation publisher (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or treatment recommendations",
        "kinase activity, generic all-omics fusion, or biomarker-panel emission",
        "unsupported-to-negative conversion or hidden attribution",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0608Request:
    request: PublishProteinAbundanceEvidenceRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0608Request, tuple[object, object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-08 execution requires a validated request token")


class M0608Plugin(
    ModulePlugin[
        object,
        ValidatedM0608Request,
        ProteinAbundanceEvidencePublicationResult,
    ]
):
    """Expose provisional M06-08 through the common plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0608Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0608Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            parsed = strict_json_loads(
                serialized,
                max_bytes=M0608_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        else:
            typed = self._service.validate_request(_prepare(candidate))
        token = ValidatedM0608Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (self, typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0608Request) -> ProteinAbundanceEvidencePublicationResult:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0608Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not self
            or snapshot[1] is not request.request
            or snapshot[2] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinAbundanceEvidencePublicationResult:
        """Verify a result through the same service boundary as execution."""

        return self._service.verify(result, replay=replay)


__all__ = ["M0608Plugin", "ValidatedM0608Request"]
