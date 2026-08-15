"""Strict validate-then-run plugin for provisional M08-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_02 import (
    M0802_CONTRACT_VERSION,
    M0802_MAX_CANONICAL_REQUEST_BYTES,
    M0802_MODULE_ID,
    ConstructTranscriptProteinRepresentationRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M0802Service

if TYPE_CHECKING:
    from .engine import BuiltRepresentation

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructTranscriptProteinRepresentationRequest)
_PROVISIONAL_DESCRIPTOR: Final = {
    "moduleId": M0802_MODULE_ID,
    "title": "Representation and feature constructor",
    "version": M0802_CONTRACT_VERSION,
    "status": "provisional",
    "operation": "construct_transcript_protein_representation",
    "parentTarget": "protein_subtype",
    "prohibitedOutputs": (
        "kinase_activity",
        "all_omics_fusion",
        "treatment_recommendation",
        "identity_inference",
    ),
}


@dataclass(frozen=True, slots=True)
class RepresentationSubmission:
    """Untrusted submission accepted only by the parse-once boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM0802Request:
    request: ConstructTranscriptProteinRepresentationRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M08-02 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M08-02 validation requires a representation submission")


class M0802Plugin:
    """Expose M08-02 through a strict, parse-once submission boundary."""

    descriptor = _PROVISIONAL_DESCRIPTOR

    def __init__(self, service: M0802Service | None = None) -> None:
        self._service = service or M0802Service()

    def validate_request(
        self,
        request: object,
    ) -> ConstructTranscriptProteinRepresentationRequest:
        return self._service.validate_request(request)

    def validate(self, submission: object) -> ValidatedM0802Request:
        if not isinstance(submission, RepresentationSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            strict_json_loads(candidate, max_bytes=M0802_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(candidate) if isinstance(candidate, bytearray) else candidate
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        return ValidatedM0802Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0802Request) -> BuiltRepresentation:
        if not isinstance(request, ValidatedM0802Request):
            raise _InvalidExecutionTokenError
        return self._service.construct(request.request)

    def construct(self, request: object) -> BuiltRepresentation:
        return self._service.construct(request)

    def execute(self, request: object) -> BuiltRepresentation:
        return self.construct(request)


__all__ = ["M0802Plugin", "RepresentationSubmission", "ValidatedM0802Request"]

