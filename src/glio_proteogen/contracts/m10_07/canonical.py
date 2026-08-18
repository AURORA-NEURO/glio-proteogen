"""Canonical projections for the provisional M10-07 contract spine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if type(value) is dict:
        return _plain_dict(value)
    raise TypeError("canonical values must be Pydantic models or exact dicts")


def _plain_dict(value: dict[str, Any]) -> dict[str, Any]:
    """Copy only built-in containers before canonical serialization."""

    return {key: _plain_value(item) for key, item in value.items()}


def _plain_value(value: object) -> object:
    if type(value) is dict:
        return _plain_dict(value)
    if type(value) is list:
        return [_plain_value(item) for item in value]
    if type(value) is tuple:
        return tuple(_plain_value(item) for item in value)
    if isinstance(value, (dict, list, tuple)):
        raise TypeError("canonical values must use built-in containers")
    return value


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


__all__ = [
    "canonical_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
]
