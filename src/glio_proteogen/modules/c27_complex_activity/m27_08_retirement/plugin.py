"""Issued-capability plugin for M27-08."""

# Capability errors are intentionally sanitized at the plugin boundary.
# ruff: noqa: TRY003, TC001

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m27_08 import (
    ComplexActivityRetirementResult,
    RetireComplexActivityServiceRequest,
)
from glio_proteogen.contracts.m27_08.canonical import canonical_request_digest
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.service import M2708Service


@dataclass(frozen=True)
class RetirementSubmission:
    request: RetireComplexActivityServiceRequest


@dataclass(frozen=True)
class _IssuedToken:
    request: RetireComplexActivityServiceRequest
    request_digest: str


class M2708Plugin:
    def __init__(self) -> None:
        self._issued: dict[int, tuple[int, str]] = {}
        self._service = M2708Service()

    def validate(self, submission: RetirementSubmission) -> _IssuedToken:
        token = _IssuedToken(submission.request, canonical_request_digest(submission.request))
        self._issued[id(token)] = (id(token.request), token.request_digest)
        return token

    def run(self, token: _IssuedToken) -> ComplexActivityRetirementResult:
        record = self._issued.get(id(token))
        if record is None or record != (id(token.request), canonical_request_digest(token.request)):
            raise ValueError("M27-08 capability is not issued or is stale")
        return self._service.execute(token.request)


__all__ = ["M2708Plugin", "RetirementSubmission"]
