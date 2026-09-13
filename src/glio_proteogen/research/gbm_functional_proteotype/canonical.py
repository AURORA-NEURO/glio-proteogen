"""Canonical projections for deterministic GBM functional-proteotype receipts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .contracts import (
        FunctionalProteotypeRequest,
        FunctionalProteotypeResult,
        ObjectiveTraceStep,
        UnverifiedFunctionalProteotypeResult,
    )


def canonical_json_bytes(value: object) -> bytes:
    """Encode JSON with stable keys and no non-finite-number extension."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_digest(value: object) -> str:
    """Return the repository's tagged SHA-256 representation."""

    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _dump(value: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return deepcopy(dict(value))


def normalized_request(
    value: FunctionalProteotypeRequest | Mapping[str, Any],
) -> dict[str, Any]:
    """Project a request so observation order has no computational meaning."""

    document = _dump(value)
    document["observations"] = sorted(
        document["observations"],
        key=lambda item: (item["gene_symbol"], item["observation_id"]),
    )
    return document


def canonical_request_digest(
    value: FunctionalProteotypeRequest | Mapping[str, Any],
) -> str:
    """Bind every caller-supplied request field in an order-invariant receipt."""

    return sha256_digest(normalized_request(value))


def computational_request_digest(
    value: FunctionalProteotypeRequest | Mapping[str, Any],
    *,
    random_profile_digest: str,
) -> str:
    """Bind the two numerical random streams and immutable algorithm profile.

    Opaque sample labels, observation labels, and provenance receipts remain bound by
    :func:`canonical_request_digest`, but do not alter deterministic random streams.
    Missing and unsupported declarations remain visible in that caller receipt while
    being absent from this numerical identity.  Requested replicate counts are also
    omitted so increasing a run extends the same deterministic random prefix.
    """

    return sha256_digest(
        {
            "bootstrap_stream_digest": bootstrap_computational_digest(
                value,
                random_profile_digest=random_profile_digest,
            ),
            "permutation_stream_digest": permutation_computational_digest(
                value,
                random_profile_digest=random_profile_digest,
            ),
        }
    )


def bootstrap_computational_digest(
    value: FunctionalProteotypeRequest | Mapping[str, Any],
    *,
    random_profile_digest: str,
) -> str:
    """Bind exactly the active evidence consumed by fit/bootstrap calculations."""

    request = normalized_request(value)
    evidence = [
        {
            "gene_symbol": item["gene_symbol"],
            "quality_weight": item["quality_weight"],
            "standard_error": item["standard_error"],
            "standardized_effect": item["standardized_effect"],
            "state": item["state"],
        }
        for item in request["observations"]
        if item["state"] in {"observed", "left_censored"}
    ]
    return sha256_digest(
        {
            "effect_scale": request["effect_scale"],
            "evidence": evidence,
            "random_profile_digest": random_profile_digest,
            "profile_id": request["profile_id"],
            "stream": "bootstrap",
        }
    )


def permutation_computational_digest(
    value: FunctionalProteotypeRequest | Mapping[str, Any],
    *,
    random_profile_digest: str,
) -> str:
    """Bind exactly the observed ranks consumed by the stratified null."""

    request = normalized_request(value)
    evidence = [
        {
            "gene_symbol": item["gene_symbol"],
            "standardized_effect": item["standardized_effect"],
        }
        for item in request["observations"]
        if item["state"] == "observed"
    ]
    return sha256_digest(
        {
            "effect_scale": request["effect_scale"],
            "evidence": evidence,
            "random_profile_digest": random_profile_digest,
            "profile_id": request["profile_id"],
            "stream": "permutation",
        }
    )


def objective_trace_digest(
    value: Sequence[ObjectiveTraceStep | Mapping[str, Any]],
) -> str:
    """Bind every paired baseline/candidate objective record."""

    rows = [
        item.model_dump(mode="json") if isinstance(item, BaseModel) else deepcopy(dict(item))
        for item in value
    ]
    return sha256_digest(rows)


def result_payload_digest(
    value: FunctionalProteotypeResult | UnverifiedFunctionalProteotypeResult | Mapping[str, Any],
) -> str:
    """Digest a result while excluding its self-referential digest field."""

    document = _dump(value)
    document.pop("result_digest", None)
    return sha256_digest(document)


def semantic_result_equal(
    left: FunctionalProteotypeResult | UnverifiedFunctionalProteotypeResult | Mapping[str, Any],
    right: FunctionalProteotypeResult | UnverifiedFunctionalProteotypeResult | Mapping[str, Any],
) -> bool:
    """Compare complete JSON semantics, including explicit absence declarations."""

    return _dump(left) == _dump(right)


__all__ = [
    "canonical_json_bytes",
    "canonical_request_digest",
    "computational_request_digest",
    "normalized_request",
    "objective_trace_digest",
    "result_payload_digest",
    "semantic_result_equal",
    "sha256_digest",
]
