"""Issued-capability plugin for M27-08."""

# Capability errors are intentionally sanitized at the plugin boundary.
# ruff: noqa: TRY003

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m27_08 import (
    ComplexActivityRetirementResult,
    RetireComplexActivityServiceRequest,
)
from glio_proteogen.contracts.m27_08.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.service import M2708Service


@dataclass(frozen=True)
class RetirementSubmission:
    request: RetireComplexActivityServiceRequest


@dataclass(frozen=True)
class _IssuedToken:
    request: RetireComplexActivityServiceRequest
    request_digest: str
    _request_identity: int = 0
    _request_bytes: bytes = b""
    _seal: object | None = None


class M2708Plugin:
    def __init__(self) -> None:
        self._issued: dict[int, tuple[int, str, bytes, object]] = {}
        self._service = M2708Service()
        self._seal = object()

    def validate(self, submission: RetirementSubmission) -> _IssuedToken:
        if not isinstance(submission, RetirementSubmission):
            raise TypeError("M27-08 capability submission is invalid")
        if type(submission.request) is not RetireComplexActivityServiceRequest:
            raise TypeError("M27-08 capability submission is invalid")
        request_bytes = canonical_json_bytes(submission.request.model_dump(mode="json"))
        token = _IssuedToken(
            submission.request,
            canonical_request_digest(submission.request),
            id(submission.request),
            request_bytes,
            self._seal,
        )
        self._issued[id(token)] = (
            id(token.request),
            token.request_digest,
            request_bytes,
            self._seal,
        )
        return token

    def run(self, token: _IssuedToken) -> ComplexActivityRetirementResult:
        record = self._issued.get(id(token))
        if (
            record is None
            or type(token) is not _IssuedToken
            or token._seal is not self._seal
            or type(token.request) is not RetireComplexActivityServiceRequest
            or record[:2] != (token._request_identity, token.request_digest)
            or record[2] != token._request_bytes
        ):
            raise ValueError("M27-08 capability is not issued or is stale")
        try:
            current_bytes = canonical_json_bytes(token.request.model_dump(mode="json"))
        except Exception as error:
            raise ValueError("M27-08 capability is not issued or is stale") from error
        if (
            id(token.request) != token._request_identity
            or current_bytes != token._request_bytes
            or canonical_request_digest(token.request) != token.request_digest
        ):
            raise ValueError("M27-08 capability is not issued or is stale")
        return self._service.execute(token.request)


__all__ = ["M2708Plugin", "RetirementSubmission"]
