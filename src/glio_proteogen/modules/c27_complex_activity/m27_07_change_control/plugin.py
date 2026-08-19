"""Issued-capability plugin boundary for M27-07."""

# ruff: noqa: TRY003

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m27_07 import (
    ComplexActivityChangeControlResult,
    ControlComplexActivityChangeRequest,
)
from glio_proteogen.contracts.m27_07.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.service import M2707Service


@dataclass(frozen=True)
class ChangeControlSubmission:
    request: ControlComplexActivityChangeRequest


@dataclass(frozen=True)
class _IssuedToken:
    request: ControlComplexActivityChangeRequest
    request_digest: str
    _request_identity: int = 0
    _request_bytes: bytes = b""
    _seal: object | None = None


class M2707Plugin:
    """Parse/validate once and issue an identity-bound execution token."""

    def __init__(self) -> None:
        self._issued: dict[int, tuple[int, str, bytes, object]] = {}
        self._service = M2707Service()
        self._seal = object()

    def validate(self, submission: ChangeControlSubmission) -> _IssuedToken:
        if not isinstance(submission, ChangeControlSubmission):
            raise TypeError("M27-07 capability submission is invalid")
        request = submission.request
        if type(request) is not ControlComplexActivityChangeRequest:
            raise TypeError("M27-07 capability submission is invalid")
        request_bytes = canonical_json_bytes(request.model_dump(mode="json"))
        token = _IssuedToken(
            request=request,
            request_digest=canonical_request_digest(request),
            _request_identity=id(request),
            _request_bytes=request_bytes,
            _seal=self._seal,
        )
        self._issued[id(token)] = (
            id(request),
            token.request_digest,
            request_bytes,
            self._seal,
        )
        return token

    def run(self, token: _IssuedToken) -> ComplexActivityChangeControlResult:
        record = self._issued.get(id(token))
        if (
            record is None
            or type(token) is not _IssuedToken
            or token._seal is not self._seal
            or type(token.request) is not ControlComplexActivityChangeRequest
            or record[:2] != (token._request_identity, token.request_digest)
            or record[2] != token._request_bytes
        ):
            raise ValueError("M27-07 capability is not issued or is stale")
        try:
            current_bytes = canonical_json_bytes(token.request.model_dump(mode="json"))
        except Exception as error:
            raise ValueError("M27-07 capability is not issued or is stale") from error
        if (
            id(token.request) != token._request_identity
            or current_bytes != token._request_bytes
            or canonical_request_digest(token.request) != token.request_digest
        ):
            raise ValueError("M27-07 capability is not issued or is stale")
        return self._service.execute(token.request)


__all__ = ["ChangeControlSubmission", "M2707Plugin"]
