"""Canonical receipts for KNCC Neftel conditional-transition concordance."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .contracts import (
        LongitudinalGbmNeftelTransitionRequest,
        LongitudinalGbmNeftelTransitionResult,
    )


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
    value: LongitudinalGbmNeftelTransitionRequest | dict[str, Any],
) -> dict[str, Any]:
    """Preserve time order while sorting set-like observations within each point."""

    document = _dump(value)
    for time_point in document["time_points"]:
        time_point["observations"] = sorted(
            time_point["observations"],
            key=lambda item: (item["gene_symbol"], item["observation_id"]),
        )
    return document


def canonical_request_digest(
    value: LongitudinalGbmNeftelTransitionRequest | dict[str, Any],
) -> str:
    return sha256_digest(normalized_request(value))


def computational_request_digest(
    value: LongitudinalGbmNeftelTransitionRequest | dict[str, Any],
    *,
    profile_digest: str,
) -> str:
    """Bind numerical evidence without letting opaque receipt IDs alter inference."""

    document = normalized_request(value)
    time_points: list[dict[str, Any]] = []
    for time_point in document["time_points"]:
        evidence = [
            {
                "gene_symbol": observation["gene_symbol"],
                "log_abundance": observation["log_abundance"],
                "quality_weight": observation["quality_weight"],
                "standard_error": observation["standard_error"],
                "state": observation["state"],
            }
            for observation in time_point["observations"]
            if observation["state"] in {"observed", "left_censored"}
        ]
        time_points.append(
            {
                "active_evidence": evidence,
                "normalization_reference_digest": time_point["normalization_reference_digest"],
                "time_offset_days": time_point["time_offset_days"],
            }
        )
    return sha256_digest(
        {
            "assay_compatibility": document["assay_compatibility"],
            "bootstrap_replicates": document["bootstrap_replicates"],
            "normalization_reference": document["normalization_reference"],
            "profile_digest": profile_digest,
            "profile_id": document["profile_id"],
            "time_points": time_points,
        }
    )


def result_payload_digest(
    value: LongitudinalGbmNeftelTransitionResult | BaseModel | dict[str, Any],
) -> str:
    document = _dump(value)
    document.pop("result_digest", None)
    return sha256_digest(document)


def profile_payload_digest(value: BaseModel | dict[str, Any]) -> str:
    document = _dump(value)
    document.pop("profile_digest", None)
    return sha256_digest(document)


__all__ = [
    "canonical_json_bytes",
    "canonical_request_digest",
    "computational_request_digest",
    "normalized_request",
    "profile_payload_digest",
    "result_payload_digest",
    "sha256_digest",
]
