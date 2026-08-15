"""Canonical projections for the provisional M08-06 contract spine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

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


def canonical_result_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    """Return the digest committed by a result envelope."""

    return result_payload_digest(value)


def verify_result_digest(value: object) -> bool:
    """Check a result digest without coercing an untrusted submission."""

    if isinstance(value, BaseModel):
        reported = getattr(value, "result_digest", None)
    elif isinstance(value, dict):
        reported = value.get("result_digest")
    else:
        return False
    if not isinstance(reported, str):
        return False
    try:
        expected = canonical_result_digest(cast("BaseModel | dict[str, Any]", value))
    except (TypeError, ValueError):
        return False
    return reported == expected


__all__ = [
    "canonical_result_digest",
    "canonical_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
    "verify_result_digest",
]
