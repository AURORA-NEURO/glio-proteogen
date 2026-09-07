"""Canonical projections for the provisional M11-04 contract spine."""

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
    document = _dump(value)
    # Typed research evidence is a set, not a sequence.  Sorting only these
    # additive fields preserves legacy request digests while making replay and
    # bootstrap seeds invariant to JSON input order.
    for field, key in (
        ("typed_observations", "observation_id"),
        ("typed_relations", "relation_id"),
    ):
        entries = document.get(field)
        if isinstance(entries, list):
            document[field] = sorted(entries, key=lambda item: str(item.get(key, "")))
    return document


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


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
    "result_payload_digest",
]
