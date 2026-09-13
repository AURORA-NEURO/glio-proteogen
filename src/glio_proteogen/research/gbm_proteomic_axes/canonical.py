"""Canonical projections for deterministic GBM proteomic-axis receipts."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from .contracts import (
        GbmProteomicAxesRequest,
        GbmProteomicAxesResult,
        UnverifiedGbmProteomicAxesResult,
    )

_DEFAULT_SIGNATURE_IDS = (
    "SWEET_KRAS_TARGETS_UP",
    "HALLMARK_MYC_TARGETS_V1",
    "WINTER_HYPOXIA_UP",
    "VERHAAK_GLIOBLASTOMA_MESENCHYMAL",
    "VERHAAK_GLIOBLASTOMA_NEURAL",
    "VERHAAK_GLIOBLASTOMA_PRONEURAL",
    "EGFR_UP.V1_UP",
)


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return deepcopy(value)


def normalized_request(
    value: GbmProteomicAxesRequest | dict[str, Any],
) -> dict[str, Any]:
    """Normalize collections whose order has no computational meaning."""

    document = _dump(value)
    document["measurements"] = sorted(
        document["measurements"], key=lambda item: item["gene_symbol"]
    )
    document["signature_ids"] = sorted(document["signature_ids"])
    return document


def request_digest(value: GbmProteomicAxesRequest | dict[str, Any]) -> str:
    """Bind all request content, including evidence provenance and sample label."""

    return sha256_digest(normalized_request(value))


def computational_request_digest(
    value: GbmProteomicAxesRequest | dict[str, Any],
) -> str:
    """Bind only fields that can change scores, support, or uncertainty."""

    document = normalized_request(value)
    selected_signatures = document["signature_ids"] or list(_DEFAULT_SIGNATURE_IDS)
    projection = {
        "computational_digest_policy": "gbm_lfq_projection_v1",
        "profile_id": document["profile_id"],
        "bootstrap_replicates": document["bootstrap_replicates"],
        "signature_ids": sorted(selected_signatures),
        "measurements": [
            {
                "gene_symbol": item["gene_symbol"],
                "lfq_intensity": item["lfq_intensity"],
                "log2_standard_error": item["log2_standard_error"],
            }
            for item in document["measurements"]
            if item["state"] == "observed"
        ],
    }
    return sha256_digest(projection)


def normalized_result_payload(
    value: GbmProteomicAxesResult | UnverifiedGbmProteomicAxesResult | dict[str, Any],
) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    return document


def result_digest(
    value: GbmProteomicAxesResult | UnverifiedGbmProteomicAxesResult | dict[str, Any],
) -> str:
    """Bind the complete result except its self-referential digest field."""

    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "computational_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "request_digest",
    "result_digest",
]
