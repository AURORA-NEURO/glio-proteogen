"""Canonical receipts for the research-only GBMPurity NumPy port."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .contracts import (
        GbmRnaPurityRequest,
        GbmRnaPurityResult,
        UnverifiedGbmRnaPurityResult,
    )


def canonical_json_bytes(value: object) -> bytes:
    """Encode strict JSON with stable keys and no non-finite extension."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _dump(value: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return deepcopy(dict(value))


def normalized_request(
    value: GbmRnaPurityRequest | Mapping[str, Any],
) -> dict[str, Any]:
    """Remove input-row ordering as a computational degree of freedom."""

    document = _dump(value)
    document["counts"] = sorted(document["counts"], key=lambda row: row["gene_symbol"])
    return document


def canonical_request_digest(
    value: GbmRnaPurityRequest | Mapping[str, Any],
) -> str:
    return sha256_digest(normalized_request(value))


def result_payload_digest(
    value: (GbmRnaPurityResult | UnverifiedGbmRnaPurityResult | Mapping[str, Any]),
) -> str:
    document = _dump(value)
    document.pop("result_digest", None)
    return sha256_digest(document)


def semantic_result_equal(
    left: GbmRnaPurityResult | UnverifiedGbmRnaPurityResult | Mapping[str, Any],
    right: GbmRnaPurityResult | UnverifiedGbmRnaPurityResult | Mapping[str, Any],
) -> bool:
    return _dump(left) == _dump(right)


__all__ = [
    "canonical_json_bytes",
    "canonical_request_digest",
    "normalized_request",
    "result_payload_digest",
    "semantic_result_equal",
    "sha256_digest",
]
