"""Canonical content bindings; collection order has no analytic meaning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from .contracts import ReplicationRequest, ReplicationResult


def canonical_request_digest(request: ReplicationRequest) -> str:
    return sha256_digest(request.model_dump(mode="json"))


def result_payload_digest(result: ReplicationResult) -> str:
    return sha256_digest(result.model_dump(mode="json", exclude={"result_digest"}))


def require_byte_limit(value: object, maximum: int) -> None:
    if len(canonical_json_bytes(value)) > maximum:
        raise ValueError("replication canonical payload exceeds its byte limit")
