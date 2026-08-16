"""Canonical projections for the provisional M07-07 contract spine."""

from __future__ import annotations

import json
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
    # These collections are sets of independently identified evidence.  Their
    # wire order is intentionally not part of the provisional semantic digest.
    policy = document.get("policy")
    if isinstance(policy, dict):
        strata = policy.get("strata")
        if isinstance(strata, (list, tuple)):
            policy["strata"] = sorted(
                strata,
                key=lambda item: (
                    str(item.get("stratum_id", ""))
                    if isinstance(item, dict)
                    else json.dumps(item, sort_keys=True)
                ),
            )
    for field, key in (("candidates", "feature_id"), ("source_artifacts", "artifact_id")):
        values = document.get(field)
        if isinstance(values, (list, tuple)):
            document[field] = sorted(
                values,
                key=lambda item: (
                    str(item.get(key, ""))
                    if isinstance(item, dict)
                    else json.dumps(item, sort_keys=True)
                ),
            )
    return document


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    request = document.get("request")
    if isinstance(request, dict):
        document["request"] = normalized_request(request)
    return document


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
]
