"""Canonical, input-order-invariant receipts for signature-transition concordance."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .contracts import LongitudinalGbmKinaseTransitionRequest


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else deepcopy(value)


def normalized_request(
    value: LongitudinalGbmKinaseTransitionRequest | dict[str, Any],
) -> dict[str, Any]:
    document = _dump(value)
    for point in document["time_points"]:
        point["observations"] = sorted(
            point["observations"],
            key=lambda item: (item["phosphosite_id"], item["observation_id"]),
        )
    return document


def canonical_request_digest(
    value: LongitudinalGbmKinaseTransitionRequest | dict[str, Any],
) -> str:
    return sha256_digest(normalized_request(value))


def computational_request_digest(
    value: LongitudinalGbmKinaseTransitionRequest | dict[str, Any],
    *,
    profile_digest: str,
) -> str:
    document = normalized_request(value)
    points = [
        {
            "time_offset_days": point["time_offset_days"],
            "normalization_reference_digest": point["normalization_reference_digest"],
            "active_evidence": [
                {
                    "phosphosite_id": item["phosphosite_id"],
                    "gene_symbol": item["gene_symbol"],
                    "state": item["state"],
                    "log_abundance_ratio": item["log_abundance_ratio"],
                    "standard_error": item["standard_error"],
                    "quality_weight": item["quality_weight"],
                }
                for item in point["observations"]
                if item["state"] in {"observed", "left_censored"}
            ],
        }
        for point in document["time_points"]
    ]
    return sha256_digest(
        {
            "profile_id": document["profile_id"],
            "profile_digest": profile_digest,
            "assay_compatibility": document["assay_compatibility"],
            "normalization_reference": document["normalization_reference"],
            "bootstrap_replicates": document["bootstrap_replicates"],
            "time_points": points,
        }
    )


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
    "computational_request_digest",
    "normalized_request",
    "profile_payload_digest",
    "result_payload_digest",
    "sha256_digest",
]
