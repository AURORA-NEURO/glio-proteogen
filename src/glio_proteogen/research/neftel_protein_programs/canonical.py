"""Canonical content projections for Neftel bulk-protein program evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .contracts import ProteinProgramRequest, ProteinProgramResult


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
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return deepcopy(value)


def normalized_request(value: ProteinProgramRequest | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document["observations"] = sorted(
        document["observations"],
        key=lambda item: (item["gene_symbol"], item["observation_id"]),
    )
    return document


def canonical_request_digest(value: ProteinProgramRequest | dict[str, Any]) -> str:
    return sha256_digest(normalized_request(value))


def computational_request_digest(
    value: ProteinProgramRequest | dict[str, Any],
    *,
    profile_digest: str,
    symbol_aliases: Mapping[str, str],
) -> str:
    """Bind the profile and alias-normalized evidence that drives computation.

    Receipt identity deliberately retains the caller's submitted symbol.  Stochastic
    identity instead projects profile-pinned aliases to the same numerical entity so
    that, for example, otherwise equivalent ``WARS`` and ``WARS1`` requests draw the
    same bootstrap and permutation streams.
    """

    document = normalized_request(value)
    active = [
        {
            "gene_symbol": symbol_aliases.get(item["gene_symbol"], item["gene_symbol"]),
            "quality_weight": item["quality_weight"],
            "standard_error": item["standard_error"],
            "standardized_effect": item["standardized_effect"],
            "state": item["state"],
        }
        for item in document["observations"]
        if item["state"] in {"observed", "left_censored"}
    ]
    return sha256_digest(
        {
            "active_evidence": sorted(active, key=lambda item: item["gene_symbol"]),
            "bootstrap_replicates": document["bootstrap_replicates"],
            "permutation_replicates": document["permutation_replicates"],
            "profile_digest": profile_digest,
            "profile_id": document["profile_id"],
        }
    )


def result_payload_digest(value: ProteinProgramResult | dict[str, Any]) -> str:
    document = _dump(value)
    document.pop("result_digest", None)
    return sha256_digest(document)


__all__ = [
    "canonical_json_bytes",
    "canonical_request_digest",
    "computational_request_digest",
    "normalized_request",
    "result_payload_digest",
    "sha256_digest",
]
