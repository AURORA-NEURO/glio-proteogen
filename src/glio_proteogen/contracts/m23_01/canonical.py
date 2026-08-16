"""Canonical projections for the provisional M23-01 contract spine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest

RESULT_ID_PREFIX = "curation.m2301."


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def result_identifier(request_digest: Sha256Digest) -> str:
    """Return the deterministic module-local identity for one request digest."""

    return f"{RESULT_ID_PREFIX}{request_digest.removeprefix('sha256:')}"


def normalized_package_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Project a package without its self-referential lock digest."""

    document = _dump(value)
    document.pop("lock_digest", None)
    return document


def package_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_package_payload(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    return document


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "normalized_package_payload",
    "normalized_request",
    "normalized_result_payload",
    "package_payload_digest",
    "result_identifier",
    "result_payload_digest",
]
