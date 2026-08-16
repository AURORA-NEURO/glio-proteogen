"""Canonical projections for the provisional M19-06 contract spine."""

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


def normalized_audit_event_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return the hashable event projection without its self-referential digest.

    Audit events are content addressed independently of the enclosing record.  This
    lets a record prove an append-only chain without requiring a recursive record
    digest (and makes replay verification independent of storage order).
    """

    document = _dump(value)
    document.pop("event_digest", None)
    return document


def audit_event_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    """Compute the canonical digest for one immutable audit event payload."""

    return sha256_digest(normalized_audit_event_payload(value))


__all__ = [
    "audit_event_payload_digest",
    "canonical_request_digest",
    "normalized_audit_event_payload",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
]
