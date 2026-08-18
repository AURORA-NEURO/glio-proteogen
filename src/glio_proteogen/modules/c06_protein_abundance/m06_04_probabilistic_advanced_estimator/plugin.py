"""Validate-then-run plugin boundary for provisional M06-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m06_04 import (
    M0604_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinAbundanceProbabilisticRequest,
    EstimateProteinAbundanceProbabilisticResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import _prepare_request, preflight_probabilistic_estimator_authorization

if TYPE_CHECKING:
    from .service import M0604Service

_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M06-04",
    title="Probabilistic and advanced protein-abundance estimator",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "calibrated posterior or clinical probability claims",
        "biomarker-panel emission, treatment recommendation, or kinase activity",
        "identity, consent, or upstream evidence inference or mutation",
    ),
)
_TOKEN_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class M0604Submission:
    request: object


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0604Request:
    """Opaque capability proving M06-04 accepted the request boundary."""

    request: EstimateProteinAbundanceProbabilisticRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0604Request, tuple[object, object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-04 execution requires a validated request token")


class M0604Plugin:
    """Expose the estimator only after strict validation and authorization."""

    __slots__ = ("_service",)

    def __init__(self, service: M0604Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, submission: M0604Submission | object) -> ValidatedM0604Request:
        candidate = submission.request if isinstance(submission, M0604Submission) else submission
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M0604_MAX_CANONICAL_REQUEST_BYTES)
            preflight_probabilistic_estimator_authorization(decoded)
        typed = _prepare_request(candidate)
        token = ValidatedM0604Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (self, typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0604Request) -> EstimateProteinAbundanceProbabilisticResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        candidate = getattr(request, "request", None)
        if (
            type(request) is not ValidatedM0604Request
            or getattr(request, "_seal", None) is not _TOKEN_SEAL
            or snapshot is None
            or not isinstance(candidate, EstimateProteinAbundanceProbabilisticRequest)
            or snapshot[0] is not self
            or snapshot[1] is not candidate
            or snapshot[2] != canonical_request_digest(candidate)
        ):
            raise _InvalidExecutionTokenError
        return self._service.estimate(candidate)


__all__ = ["M0604Plugin", "M0604Submission", "ValidatedM0604Request"]
