"""Strict validate-then-run plugin boundary for provisional M05-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m05_06 import (
    M0506_MAX_CANONICAL_REQUEST_BYTES,
    HarmonizePtmLocalizationAnalysisRequest,
    PtmLocalizationHarmonizationResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.engine import (
    _prepare,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.service import (
        M0506Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M05-06",
    title="PTM-localization harmonization and normalization (provisional)",
    version="1.0.0-provisional",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or abundance measurements",
        "identity, consent, PTM localization, kinase, subtype, proteotype, or treatment inference",
        "calibrated probability or external content traversal",
        "upstream mutation, relabeling, missing-as-negative conversion, or disagreement erasure",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0506Request:
    request: HarmonizePtmLocalizationAnalysisRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0506Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-06 execution requires a validated request token")


class M0506Plugin(ModulePlugin[object, ValidatedM0506Request, PtmLocalizationHarmonizationResult]):
    """Expose M05-06 through the common plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0506Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0506Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(serialized, max_bytes=M0506_MAX_CANONICAL_REQUEST_BYTES)
        typed = self._service.validate_request(_prepare(candidate))
        token = ValidatedM0506Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0506Request) -> PtmLocalizationHarmonizationResult:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0506Request
            or getattr(request, "_seal", None) is not _TOKEN_SEAL
            or snapshot is None
            or getattr(request, "request", None) is not snapshot[0]
            or snapshot[1] != canonical_request_digest(getattr(request, "request", None))
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0506Plugin", "ValidatedM0506Request"]
