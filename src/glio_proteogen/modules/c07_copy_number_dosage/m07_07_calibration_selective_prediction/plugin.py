"""Strict validate-then-run plugin boundary for provisional M07-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m07_07 import (
    M0707_MAX_CANONICAL_REQUEST_BYTES,
    CalibrateSelectiveCopyNumberDosageRequest,
    CalibrateSelectiveCopyNumberDosageResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from .service import M0707Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M07-07",
    title="copy-number dosage calibration and selective prediction (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or treatment recommendations",
        "kinase activity, generic all-omics fusion, or parent proteotype emission",
        "unsupported-to-negative conversion or unqualified calibration claims",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0707Request:
    request: CalibrateSelectiveCopyNumberDosageRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0707Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-07 execution requires a validated request token")


class M0707Plugin(
    ModulePlugin[
        object,
        ValidatedM0707Request,
        CalibrateSelectiveCopyNumberDosageResult,
    ]
):
    """Expose M07-07 through the common plugin ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: M0707Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0707Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0707_MAX_CANONICAL_REQUEST_BYTES,
            )
        typed = self._service.validate_request(candidate)
        token = ValidatedM0707Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0707Request) -> CalibrateSelectiveCopyNumberDosageResult:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0707Request
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
        request: object | None = None,
    ) -> CalibrateSelectiveCopyNumberDosageResult:
        """Verify canonical result and optional request binding for replay."""

        return self._service.verify_result(result, request)


__all__ = ["M0707Plugin", "ValidatedM0707Request"]
