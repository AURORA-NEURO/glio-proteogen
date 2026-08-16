"""Strict validate-then-run plugin for provisional M06-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_05 import (
    M0605_CONTRACT_VERSION,
    M0605_MAX_CANONICAL_REQUEST_BYTES,
    M0605_MODULE_ID,
    IntegrateProteinAbundanceConstraintsRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M0605Service

if TYPE_CHECKING:
    from .engine import BuiltConstraintIntegration

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteinAbundanceConstraintsRequest)
_PROVISIONAL_DESCRIPTOR: Final = {
    "moduleId": M0605_MODULE_ID,
    "title": "Mechanism and constraint integrator",
    "version": M0605_CONTRACT_VERSION,
    "status": "provisional",
    "operation": "integrate_protein_abundance_constraints",
    "prohibitedOutputs": (
        "kinase_activity",
        "all_omics_fusion",
        "treatment_recommendation",
        "identity_inference",
        "parent_biomarker_panel",
    ),
}


@dataclass(frozen=True, slots=True)
class ConstraintIntegrationSubmission:
    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM0605Request:
    request: IntegrateProteinAbundanceConstraintsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-05 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-05 validation requires a constraint integration submission")


class M0605Plugin:
    """Expose M06-05 through a strict, parse-once submission boundary."""

    descriptor = _PROVISIONAL_DESCRIPTOR

    def __init__(self, service: M0605Service | None = None) -> None:
        self._service = service or M0605Service()

    def validate_request(self, request: object) -> IntegrateProteinAbundanceConstraintsRequest:
        return self._service.validate_request(request)

    def validate(self, submission: object) -> ValidatedM0605Request:
        if not isinstance(submission, ConstraintIntegrationSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            strict_json_loads(candidate, max_bytes=M0605_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(candidate) if isinstance(candidate, bytearray) else candidate
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        return ValidatedM0605Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0605Request) -> BuiltConstraintIntegration:
        if not isinstance(request, ValidatedM0605Request):
            raise _InvalidExecutionTokenError
        return self._service.integrate(request.request)

    def integrate(self, request: object) -> BuiltConstraintIntegration:
        return self._service.integrate(request)

    def execute(self, request: object) -> BuiltConstraintIntegration:
        return self.integrate(request)


__all__ = [
    "ConstraintIntegrationSubmission",
    "M0605Plugin",
    "ValidatedM0605Request",
]
