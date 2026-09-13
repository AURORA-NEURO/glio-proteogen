"""Canonical receipts for the independent KNCC GBM factor-graph composition."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.research.longitudinal_gbm_kinase_transition.canonical import (
    normalized_request as normalized_kinase_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.canonical import (
    normalized_request as normalized_reactome_request,
)

if TYPE_CHECKING:
    from .contracts import KnccGbmFactorGraphRequest


def canonical_json_bytes(value: object) -> bytes:
    """Encode finite JSON with stable keys and no platform-specific whitespace."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_digest(value: object) -> str:
    """Return the repository's typed SHA-256 representation."""

    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return deepcopy(value)


def normalized_request(
    value: KnccGbmFactorGraphRequest | dict[str, Any],
) -> dict[str, Any]:
    """Normalize each child with its own locked modality-specific rules."""

    document = _dump(value)
    document["reactome_request"] = normalized_reactome_request(document["reactome_request"])
    document["kinase_request"] = normalized_kinase_request(document["kinase_request"])
    return document


def canonical_request_digest(
    value: KnccGbmFactorGraphRequest | dict[str, Any],
) -> str:
    return sha256_digest(normalized_request(value))


def topology_payload_digest(value: BaseModel | dict[str, Any]) -> str:
    document = _dump(value)
    document.pop("topology_digest", None)
    return sha256_digest(document)


def profile_payload_digest(value: BaseModel | dict[str, Any]) -> str:
    document = _dump(value)
    document.pop("profile_digest", None)
    return sha256_digest(document)


def result_payload_digest(value: BaseModel | dict[str, Any]) -> str:
    document = _dump(value)
    document.pop("result_digest", None)
    return sha256_digest(document)


__all__ = [
    "canonical_json_bytes",
    "canonical_request_digest",
    "normalized_request",
    "profile_payload_digest",
    "result_payload_digest",
    "sha256_digest",
    "topology_payload_digest",
]
