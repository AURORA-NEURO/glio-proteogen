"""Canonical projections for the provisional M24-08 contract spine."""

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


def release_record_signature_digest(
    request_digest: Sha256Digest | str,
    value: BaseModel | dict[str, Any],
) -> Sha256Digest:
    """Digest every signed release field while excluding the signature itself."""

    record = _dump(value)
    record.pop("signature_digest", None)
    return sha256_digest({"request_digest": request_digest, "release_record": record})


def result_identifier(request_digest: Sha256Digest) -> str:
    """Return the deterministic M24-08 result identifier for a request digest."""

    return "gate.m2408." + request_digest.removeprefix("sha256:")


__all__ = [
    "canonical_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "release_record_signature_digest",
    "result_identifier",
    "result_payload_digest",
]
