"""Strict parse-once plugin boundary for provisional M07-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_01 import (
    M0701_CONTRACT_VERSION,
    M0701_MAX_CANONICAL_REQUEST_BYTES,
    M0701_MODULE_ID,
    ValidateCopyNumberStateRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M0701Service

if TYPE_CHECKING:
    from .engine import BuiltFormalStateResult

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateCopyNumberStateRequest)


@dataclass(frozen=True, slots=True)
class FormalStateSubmission:
    """Explicit submission wrapper prevents accidental double parsing."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM0701Request:
    request: ValidateCopyNumberStateRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-01 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-01 validation requires a formal-state submission")


class M0701Plugin:
    """Parse a bounded JSON request once, then execute only its capability token."""

    descriptor: Final = {
        "moduleId": M0701_MODULE_ID,
        "title": "Formal state and feature schema",
        "version": M0701_CONTRACT_VERSION,
        "status": "provisional",
        "operation": "validate_copy_number_formal_state",
        "parentTarget": "proteotype",
        "prohibitedOutputs": (
            "kinase_activity",
            "all_omics_fusion",
            "treatment_recommendation",
            "identity_inference",
        ),
    }

    __slots__ = ("_service",)

    def __init__(self, service: M0701Service | None = None) -> None:
        self._service = service or M0701Service()

    def validate_request(self, request: object) -> ValidateCopyNumberStateRequest:
        return self._service.validate_request(request)

    def validate(self, submission: object) -> ValidatedM0701Request:
        if not isinstance(submission, FormalStateSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            strict_json_loads(candidate, max_bytes=M0701_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(candidate) if isinstance(candidate, bytearray) else candidate
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        return ValidatedM0701Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0701Request) -> BuiltFormalStateResult:
        if not isinstance(request, ValidatedM0701Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def execute(self, request: object) -> BuiltFormalStateResult:
        return self._service.execute(request)


__all__ = ["FormalStateSubmission", "M0701Plugin", "ValidatedM0701Request"]
