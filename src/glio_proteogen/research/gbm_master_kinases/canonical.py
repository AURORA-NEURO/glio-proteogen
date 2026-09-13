"""Canonical receipt projections for master-kinase signature concordance."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .contracts import MasterKinaseRequest, MasterKinaseResult


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


def normalized_request(value: MasterKinaseRequest | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document["observations"] = sorted(
        document["observations"],
        key=lambda item: (item["phosphosite_id"], item["observation_id"]),
    )
    return document


def canonical_request_digest(value: MasterKinaseRequest | dict[str, Any]) -> str:
    return sha256_digest(normalized_request(value))


def computational_request_digest(
    value: MasterKinaseRequest | dict[str, Any],
    *,
    profile_digest: str,
) -> str:
    document = normalized_request(value)
    active = [
        {
            "phosphosite_id": item["phosphosite_id"],
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
            "active_evidence": active,
            "bootstrap_replicates": document["bootstrap_replicates"],
            "contrast_reference": document["contrast_reference"],
            "permutation_replicates": document["permutation_replicates"],
            "profile_digest": profile_digest,
            "profile_id": document["profile_id"],
        }
    )


def result_payload_digest(value: MasterKinaseResult | dict[str, Any]) -> str:
    document = _dump(value)
    document.pop("result_digest", None)
    return sha256_digest(document)


def demo_result_oracle_projection(
    value: MasterKinaseResult | dict[str, Any],
) -> dict[str, Any]:
    """Project deterministic scientific point outputs for the locked demo oracle.

    Bootstrap intervals, permutation statistics, seeds, and receipt metadata are
    intentionally excluded.  Those fields depend on the profile digest that binds
    this oracle, whereas point estimates, support inventories, drivers, and
    ablations provide a non-circular executable check of the numerical engine.
    """

    document = _dump(value)
    kinases: list[dict[str, Any]] = []
    for item in document["kinase_evidence"]:
        location = item["location"]
        rank = item["rank_enrichment"]
        kinases.append(
            {
                "edge_ablations": item["edge_ablations"],
                "evidence_counts": item["evidence_counts"],
                "kinase_id": item["kinase_id"],
                "location": {
                    "effective_sample_size": location["effective_sample_size"],
                    "reason": location["reason"],
                    "score": location["score"],
                    "support": location["support"],
                },
                "rank_enrichment": {
                    "effective_sample_size": rank["effective_sample_size"],
                    "mapped_signature_sites": rank["mapped_signature_sites"],
                    "observed_background_sites": rank["observed_background_sites"],
                    "reason": rank["reason"],
                    "score": rank["score"],
                    "support": rank["support"],
                },
                "source_kinase_label": item["source_kinase_label"],
                "source_reference": item["source_reference"],
                "source_subtype": item["source_subtype"],
                "top_drivers": item["top_drivers"],
            }
        )
    subtypes: list[dict[str, Any]] = []
    for item in document["subtype_evidence"]:
        aggregate = item["aggregate"]
        subtypes.append(
            {
                "aggregate": {
                    "effective_sample_size": aggregate["effective_sample_size"],
                    "reason": aggregate["reason"],
                    "score": aggregate["score"],
                    "support": aggregate["support"],
                },
                "estimated_member_count": item["estimated_member_count"],
                "member_kinases": item["member_kinases"],
                "subtype_ablations": item["subtype_ablations"],
                "subtype_id": item["subtype_id"],
                "supported_member_count": item["supported_member_count"],
                "top_kinases": item["top_kinases"],
            }
        )
    return {
        "algorithm_id": document["algorithm_id"],
        "algorithm_version": document["algorithm_version"],
        "contrast_reference": document["contrast_reference"],
        "kinase_evidence": kinases,
        "output_semantics": document["output_semantics"],
        "sample_id": document["sample_id"],
        "subtype_evidence": subtypes,
    }


__all__ = [
    "canonical_json_bytes",
    "canonical_request_digest",
    "computational_request_digest",
    "demo_result_oracle_projection",
    "normalized_request",
    "result_payload_digest",
    "sha256_digest",
]
