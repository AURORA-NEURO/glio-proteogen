"""Validate-then-run plugin boundary for provisional M06-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from glio_proteogen.contracts.m06_04 import (
    M0604_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinAbundanceProbabilisticRequest,
    EstimateProteinAbundanceProbabilisticResult,
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


@dataclass(frozen=True, slots=True)
class M0604Submission:
    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM0604Request:
    """Opaque capability proving M06-04 accepted the request boundary."""

    request: EstimateProteinAbundanceProbabilisticRequest
    _seal: object


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
        return ValidatedM0604Request(request=_prepare_request(candidate), _seal=self)

    def run(self, request: ValidatedM0604Request) -> EstimateProteinAbundanceProbabilisticResult:
        if not isinstance(request, ValidatedM0604Request) or request._seal is not self:
            raise _InvalidExecutionTokenError
        return self._service.estimate(request.request)


__all__ = ["M0604Plugin", "M0604Submission", "ValidatedM0604Request"]
