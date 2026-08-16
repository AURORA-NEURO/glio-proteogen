"""Canonical projections for the provisional M08-07 contract spine."""

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


def verify_result_replay(
    value: BaseModel | dict[str, Any],
    request: BaseModel | dict[str, Any] | None = None,
) -> bool:
    """Verify request binding and result digest without executing the engine."""

    document = normalized_result_payload(value)
    expected_result = cast("str", _dump(value).get("result_digest"))
    request_document = document.get("request")
    if not isinstance(request_document, dict):
        return False
    expected_request = cast("str", document.get("request_digest"))
    if expected_request != canonical_request_digest(request_document):
        return False
    if request is not None and expected_request != canonical_request_digest(request):
        return False
    return expected_result == result_payload_digest(value)


__all__ = [
    "canonical_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
    "verify_result_replay",
]
