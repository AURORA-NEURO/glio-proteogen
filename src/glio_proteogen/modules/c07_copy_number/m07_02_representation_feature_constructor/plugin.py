"""Strict validate-then-run plugin for provisional M07-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_02 import (
    M0702_CONTRACT_VERSION,
    M0702_MAX_CANONICAL_REQUEST_BYTES,
    M0702_MODULE_ID,
    ConstructProteotypeAnalysisRepresentationRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M0702Service

if TYPE_CHECKING:
    from .engine import BuiltRepresentation

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructProteotypeAnalysisRepresentationRequest)
_PROVISIONAL_DESCRIPTOR: Final = {
    "moduleId": M0702_MODULE_ID,
    "title": "Representation and feature constructor",
    "version": M0702_CONTRACT_VERSION,
    "status": "provisional",
    "operation": "construct_proteotype_analysis_representation",
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
class ValidatedM0702Request:
    request: ConstructProteotypeAnalysisRepresentationRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-02 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-02 validation requires a representation submission")


class M0702Plugin:
    """Expose M07-02 through a strict, parse-once submission boundary."""

    descriptor = _PROVISIONAL_DESCRIPTOR

    def __init__(self, service: M0702Service | None = None) -> None:
        self._service = service or M0702Service()

    def validate_request(
        self,
        request: object,
    ) -> ConstructProteotypeAnalysisRepresentationRequest:
        return self._service.validate_request(request)

    def validate(self, submission: object) -> ValidatedM0702Request:
        if not isinstance(submission, RepresentationSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            strict_json_loads(candidate, max_bytes=M0702_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(candidate) if isinstance(candidate, bytearray) else candidate
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        return ValidatedM0702Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0702Request) -> BuiltRepresentation:
        if not isinstance(request, ValidatedM0702Request):
            raise _InvalidExecutionTokenError
        return self._service.construct(request.request)

    def construct(self, request: object) -> BuiltRepresentation:
        return self._service.construct(request)

    def execute(self, request: object) -> BuiltRepresentation:
        return self.construct(request)


__all__ = ["M0702Plugin", "RepresentationSubmission", "ValidatedM0702Request"]
