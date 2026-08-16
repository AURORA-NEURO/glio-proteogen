"""Strict validate-then-run plugin for provisional M07-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_05 import (
    M0705_CONTRACT_VERSION,
    M0705_MAX_CANONICAL_REQUEST_BYTES,
    M0705_MODULE_ID,
    IntegrateProteotypeConstraintsRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M0705Service

if TYPE_CHECKING:
    from .engine import BuiltConstraintIntegration

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteotypeConstraintsRequest)
_PROVISIONAL_DESCRIPTOR: Final = {
    "moduleId": M0705_MODULE_ID,
    "title": "Mechanism and constraint integrator",
    "version": M0705_CONTRACT_VERSION,
    "status": "provisional",
    "operation": "integrate_proteotype_constraints",
    "prohibitedOutputs": (
        "kinase_activity",
        "all_omics_fusion",
        "treatment_recommendation",
        "identity_inference",
    ),
}


@dataclass(frozen=True, slots=True)
class ConstraintSubmission:
    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM0705Request:
    request: IntegrateProteotypeConstraintsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-05 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-05 validation requires a constraint submission")


class M0705Plugin:
    """Expose M07-05 through a strict, parse-once submission boundary."""

    descriptor = _PROVISIONAL_DESCRIPTOR

    def __init__(self, service: M0705Service | None = None) -> None:
        self._service = service or M0705Service()

    def validate_request(self, request: object) -> IntegrateProteotypeConstraintsRequest:
        return self._service.validate_request(request)

    def validate(self, submission: object) -> ValidatedM0705Request:
        if not isinstance(submission, ConstraintSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            strict_json_loads(candidate, max_bytes=M0705_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(candidate) if isinstance(candidate, bytearray) else candidate
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        return ValidatedM0705Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0705Request) -> BuiltConstraintIntegration:
        if not isinstance(request, ValidatedM0705Request):
            raise _InvalidExecutionTokenError
        return self._service.integrate(request.request)

    def integrate(self, request: object) -> BuiltConstraintIntegration:
        return self._service.integrate(request)

    def execute(self, request: object) -> BuiltConstraintIntegration:
        return self.integrate(request)


__all__ = ["ConstraintSubmission", "M0705Plugin", "ValidatedM0705Request"]
