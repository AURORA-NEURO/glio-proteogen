"""Issued-capability plugin boundary for M27-07."""

# ruff: noqa: TRY003, TC001

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m27_07 import (
    ComplexActivityChangeControlResult,
    ControlComplexActivityChangeRequest,
)
from glio_proteogen.contracts.m27_07.canonical import canonical_request_digest
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.service import M2707Service


@dataclass(frozen=True)
class ChangeControlSubmission:
    request: ControlComplexActivityChangeRequest


@dataclass(frozen=True)
class _IssuedToken:
    request: ControlComplexActivityChangeRequest
    request_digest: str


class M2707Plugin:
    """Parse/validate once and issue an identity-bound execution token."""

    def __init__(self) -> None:
        self._issued: dict[int, tuple[int, str]] = {}
        self._service = M2707Service()

    def validate(self, submission: ChangeControlSubmission) -> _IssuedToken:
        request = submission.request
        token = _IssuedToken(request=request, request_digest=canonical_request_digest(request))
        self._issued[id(token)] = (id(request), token.request_digest)
        return token

    def run(self, token: _IssuedToken) -> ComplexActivityChangeControlResult:
        record = self._issued.get(id(token))
        if record is None or record != (id(token.request), canonical_request_digest(token.request)):
            raise ValueError("M27-07 capability is not issued or is stale")
        return self._service.execute(token.request)


__all__ = ["ChangeControlSubmission", "M2707Plugin"]
