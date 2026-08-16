"""Strict validate-then-run plugin for M06-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_02 import (
    M0602_CONTRACT_VERSION,
    M0602_MAX_CANONICAL_REQUEST_BYTES,
    M0602_MODULE_ID,
    BuildProteinRepresentationRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M0602Service

if TYPE_CHECKING:
    from .engine import BuiltProteinRepresentation

_REQUEST_ADAPTER: Final = TypeAdapter(BuildProteinRepresentationRequest)
_PROVISIONAL_DESCRIPTOR: Final = {
    "moduleId": M0602_MODULE_ID,
    "title": "Representation and feature constructor",
    "version": M0602_CONTRACT_VERSION,
    "status": "provisional",
    "operation": "construct_protein_representation",
    "prohibitedOutputs": (
        "kinase_activity",
        "all_omics_fusion",
        "treatment_recommendation",
        "identity_inference",
    ),
}


@dataclass(frozen=True, slots=True)
class RepresentationSubmission:
    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM0602Request:
    request: BuildProteinRepresentationRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-02 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-02 validation requires a representation submission")


class M0602Plugin:
    """Expose M06-02 through a strict, parse-once submission boundary."""

    descriptor = _PROVISIONAL_DESCRIPTOR

    def __init__(self, service: M0602Service | None = None) -> None:
        self._service = service or M0602Service()

    def validate_request(self, request: object) -> BuildProteinRepresentationRequest:
        return self._service.validate_request(request)

    def validate(self, submission: object) -> ValidatedM0602Request:
        if not isinstance(submission, RepresentationSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            strict_json_loads(candidate, max_bytes=M0602_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(candidate) if isinstance(candidate, bytearray) else candidate
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        return ValidatedM0602Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0602Request) -> BuiltProteinRepresentation:
        if not isinstance(request, ValidatedM0602Request):
            raise _InvalidExecutionTokenError
        return self._service.construct(request.request)

    def construct(self, request: object) -> BuiltProteinRepresentation:
        return self._service.construct(request)

    def execute(self, request: object) -> BuiltProteinRepresentation:
        return self.construct(request)


__all__ = [
    "M0602Plugin",
    "RepresentationSubmission",
    "ValidatedM0602Request",
]
