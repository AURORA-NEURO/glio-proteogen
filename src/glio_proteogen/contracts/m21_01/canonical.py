"""Canonical projections for the provisional M21-01 contract spine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        # Preserve datetime/enum objects until the kernel canonicalizer applies
        # one deterministic representation.  JSON-mode dumping would omit
        # zero microseconds and make replay hashes depend on the construction
        # path rather than the immutable model value.
        return value.model_dump(mode="python")
    return dict(value)


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    return document


def normalized_package_lock_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return the package projection covered by its lock digest.

    ``lock_digest`` is deliberately excluded so the digest is self-consistent:
    a verifier can recompute it from the immutable package without a circular
    hash construction.  The lock still covers the endpoint, every reference,
    control, inclusion, adjudication, challenge-set id, configuration, and
    package evidence.
    """

    document = _dump(value)
    document.pop("lock_digest", None)
    return document


def package_lock_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    """Return the deterministic lock digest for a reference-truth package."""

    return sha256_digest(normalized_package_lock_payload(value))


def result_identifier(request: BaseModel | dict[str, Any]) -> str:
    """Return the deterministic result identifier bound to one request."""

    return "m2101.result." + canonical_request_digest(request).removeprefix("sha256:")


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "normalized_package_lock_payload",
    "normalized_request",
    "normalized_result_payload",
    "package_lock_digest",
    "result_identifier",
    "result_payload_digest",
]
