"""Canonical projections and content digests for provisional M05-06."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, tuple):
        return tuple(_dump(item) for item in value)
    if isinstance(value, list):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _without(value: BaseModel | dict[str, Any], *fields: str) -> dict[str, Any]:
    document = cast("dict[str, Any]", _dump(value))
    for field in fields:
        document.pop(field, None)
    return document


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", _dump(value))


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", _dump(value))


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"policy": normalized_policy(value)})


def target_binding_digest(value: tuple[object, ...]) -> Sha256Digest:
    return sha256_digest(tuple(_dump(item) for item in value))


def normalized_artifact_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", _dump(value))


def artifact_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_without(value, "receipt_digest"))


def normalized_support_ledger(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", _dump(value))


def support_ledger_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_without(value, "ledger_digest"))


def normalized_analysis(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", _dump(value))


def analysis_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_without(value, "analysis_digest"))


def normalized_manifest(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", _dump(value))


def manifest_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_without(value, "manifest_digest"))


def normalized_computation_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", _dump(value))


def computation_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_without(value, "receipt_digest"))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _without(value, "result_digest")


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "analysis_digest",
    "artifact_receipt_digest",
    "canonical_request_digest",
    "computation_receipt_digest",
    "configuration_digest",
    "manifest_digest",
    "normalized_analysis",
    "normalized_artifact_receipt",
    "normalized_computation_receipt",
    "normalized_manifest",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "normalized_support_ledger",
    "policy_digest",
    "result_payload_digest",
    "support_ledger_digest",
    "target_binding_digest",
]
