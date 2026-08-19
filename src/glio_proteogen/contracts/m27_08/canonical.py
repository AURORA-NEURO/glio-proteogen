"""Canonical projections for the provisional M27-08 contract spine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest

_SHA256_DIGEST_LENGTH: Final = 71


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def result_id_for_request_digest(value: Sha256Digest | str) -> str:
    """Return the deterministic provisional result identity for one request."""

    text = str(value)
    if not text.startswith("sha256:") or len(text) != _SHA256_DIGEST_LENGTH:
        raise ValueError("request digest must be a canonical sha256 digest")
    return f"result.m2708.{text.removeprefix('sha256:')}"


def package_id_for_request_digest(value: Sha256Digest | str) -> str:
    """Return the deterministic provisional package identity for one request."""

    text = str(value)
    if not text.startswith("sha256:") or len(text) != _SHA256_DIGEST_LENGTH:
        raise ValueError("request digest must be a canonical sha256 digest")
    return f"package.m2708.{text.removeprefix('sha256:')[:16]}"


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    return document


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "package_id_for_request_digest",
    "result_id_for_request_digest",
    "result_payload_digest",
]
