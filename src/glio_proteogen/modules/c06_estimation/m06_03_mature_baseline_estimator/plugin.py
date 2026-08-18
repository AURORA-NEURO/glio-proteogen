"""Sealed validate-then-run plugin for provisional M06-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m06_03 import (
    M0603_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinAbundanceBaselineRequest,
    EstimateProteinAbundanceBaselineResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.service import (
        M0603Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M06-03",
    title="Mature baseline protein-abundance estimator (provisional)",
    version="0.1.0-provisional",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, sequences, accessions, or abundance measurements",
        "identity, consent, biomarker-panel, clinical, or treatment inference",
        "calibrated probability, external traversal, or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0603Request:
    request: EstimateProteinAbundanceBaselineRequest
    _seal: object


_ISSUED: Final[WeakKeyDictionary[ValidatedM0603Request, tuple[object, object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-03 execution requires a validated request token")


class M0603Plugin(
    ModulePlugin[object, ValidatedM0603Request, EstimateProteinAbundanceBaselineResult]
):
    __slots__ = ("_service",)

    def __init__(self, service: M0603Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0603Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            decoded = strict_json_loads(serialized, max_bytes=M0603_MAX_CANONICAL_REQUEST_BYTES)
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = self._service.validate_request(candidate)
        token = ValidatedM0603Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED[token] = (self, typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0603Request) -> EstimateProteinAbundanceBaselineResult:
        try:
            snapshot = _ISSUED.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        candidate = getattr(request, "request", None)
        if (
            type(request) is not ValidatedM0603Request
            or getattr(request, "_seal", None) is not _TOKEN_SEAL
            or snapshot is None
            or not isinstance(candidate, EstimateProteinAbundanceBaselineRequest)
            or snapshot[0] is not self
            or snapshot[1] is not candidate
            or snapshot[2] != canonical_request_digest(candidate)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0603Plugin", "ValidatedM0603Request"]
