"""Canonical projections for deterministic research graph inference."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .contracts import (
        ProteogenomicStateRequest,
        ProteogenomicStateResult,
        UnverifiedProteogenomicStateResult,
    )


def canonical_json_bytes(value: object) -> bytes:
    """Encode a JSON-compatible value without platform-dependent whitespace."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_digest(value: object) -> str:
    """Return a lowercase, prefixed SHA-256 digest of canonical JSON."""

    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    # Request normalization sorts nested collections.  A shallow ``dict(value)``
    # would therefore mutate caller-owned external-profile data in place.
    return deepcopy(value)


def normalized_request(
    value: ProteogenomicStateRequest | dict[str, Any],
) -> dict[str, Any]:
    """Project semantically unordered request collections into stable order."""

    document = _dump(value)
    document["nodes"] = sorted(document["nodes"], key=lambda item: item["node_id"])
    document["edges"] = sorted(document["edges"], key=lambda item: item["edge_id"])
    document["observations"] = sorted(
        document["observations"], key=lambda item: item["observation_id"]
    )
    external = document.get("external_kinase_profile")
    if external is not None:
        external["estimates"] = sorted(external["estimates"], key=lambda item: item["kinase_id"])
    topology = document.get("topology_provenance")
    if topology is not None:
        topology["sources"] = sorted(topology["sources"], key=lambda item: item["source_id"])
        for source in topology["sources"]:
            source["scope_node_ids"] = sorted(source["scope_node_ids"])
    else:
        # Preserve pre-provenance request digests when the optional declaration is absent.
        document.pop("topology_provenance", None)
    return document


def graph_topology_digest(value: BaseModel | dict[str, Any]) -> str:
    """Digest only normalized nodes and edges, independent of samples and evidence."""

    document = _dump(value)
    nodes = [
        item.model_dump(mode="json") if isinstance(item, BaseModel) else item
        for item in document["nodes"]
    ]
    edges = [
        item.model_dump(mode="json") if isinstance(item, BaseModel) else item
        for item in document["edges"]
    ]
    topology = {
        "edges": sorted(edges, key=lambda item: item["edge_id"]),
        "nodes": sorted(nodes, key=lambda item: item["node_id"]),
    }
    return sha256_digest(topology)


def canonical_request_digest(
    value: ProteogenomicStateRequest | dict[str, Any],
) -> str:
    return sha256_digest(normalized_request(value))


def computational_request_digest(
    value: ProteogenomicStateRequest | dict[str, Any],
) -> str:
    """Digest only fields that can alter numerical inference.

    Receipt identity intentionally remains broader: sample labels, display labels,
    provenance declarations, inactive evidence, and external comparison profiles are
    bound by :func:`canonical_request_digest`, but cannot reseed permutations or
    bootstrap perturbations.
    """

    document = normalized_request(value)
    projection = {
        "computational_digest_policy": "explicit_numerical_projection_v1",
        "profile_id": document["profile_id"],
        "bootstrap_replicates": document["bootstrap_replicates"],
        "permutation_replicates": document["permutation_replicates"],
        "nodes": [{"node_id": item["node_id"], "kind": item["kind"]} for item in document["nodes"]],
        "edges": [
            {
                "edge_id": item["edge_id"],
                "source_id": item["source_id"],
                "target_id": item["target_id"],
                "kind": item["kind"],
                "sign": item["sign"],
                "weight": item["weight"],
                "essential": item["essential"],
            }
            for item in document["edges"]
        ],
        "observations": [
            {
                "observation_id": item["observation_id"],
                "node_id": item["node_id"],
                "modality": item["modality"],
                "state": item["state"],
                "standardized_effect": item["standardized_effect"],
                "standard_error": item["standard_error"],
                "quality_weight": item["quality_weight"],
            }
            for item in document["observations"]
            if item["state"] in {"observed", "left_censored"}
        ],
    }
    return sha256_digest(projection)


def normalized_result_payload(
    value: ProteogenomicStateResult | UnverifiedProteogenomicStateResult | dict[str, Any],
) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    return document


def result_payload_digest(
    value: ProteogenomicStateResult | UnverifiedProteogenomicStateResult | dict[str, Any],
) -> str:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_json_bytes",
    "canonical_request_digest",
    "computational_request_digest",
    "graph_topology_digest",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
    "sha256_digest",
]
