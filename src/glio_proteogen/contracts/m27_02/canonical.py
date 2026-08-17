"""Canonical projections for the provisional M27-02 contract spine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    return document


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


def graph_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    """Digest graph content while excluding the manifest's derived digest field.

    The reproducibility manifest is part of the graph envelope, so hashing it
    verbatim would require a cryptographic fixed point.  The manifest digest
    instead binds every graph field other than that derived field.
    """

    document = _dump(value)
    bundle = document.get("reproducibility_bundle")
    if isinstance(bundle, dict):
        bundle.pop("manifest_digest", None)
    return sha256_digest(document)


__all__ = [
    "canonical_request_digest",
    "graph_payload_digest",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
]
