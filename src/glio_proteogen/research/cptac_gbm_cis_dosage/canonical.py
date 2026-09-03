"""Canonical receipts for local-only CPTAC GBM cis-dosage evidence."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from .contracts import CisDosageEvidenceRequest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else deepcopy(value)


def normalized_request(
    value: CisDosageEvidenceRequest | dict[str, Any],
) -> dict[str, Any]:
    """Return an input-order-invariant query payload."""

    document = _dump(value)
    document["gene_symbols"] = sorted(document["gene_symbols"])
    return document


def request_digest(value: CisDosageEvidenceRequest | dict[str, Any]) -> str:
    return sha256_digest(normalized_request(value))


def profile_digest(value: BaseModel | dict[str, Any]) -> str:
    document = _dump(value)
    document.pop("profile_digest", None)
    return sha256_digest(document)


def artifact_content_digest(value: dict[str, Any]) -> str:
    document = deepcopy(value)
    document.pop("artifact_content_digest", None)
    return sha256_digest(document)


def result_digest(value: BaseModel | dict[str, Any]) -> str:
    document = _dump(value)
    document.pop("result_digest", None)
    return sha256_digest(document)


__all__ = [
    "artifact_content_digest",
    "normalized_request",
    "profile_digest",
    "request_digest",
    "result_digest",
]
