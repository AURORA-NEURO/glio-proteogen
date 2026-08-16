"""Canonical projections for the provisional M22-03 contract spine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    return document


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


def result_identifier(value: BaseModel | dict[str, Any]) -> str:
    """Return the deterministic provisional result identity for a request."""

    digest = canonical_request_digest(value)
    return f"m2203-result:{digest.removeprefix('sha256:')}"


__all__ = [
    "canonical_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "result_identifier",
    "result_payload_digest",
]
