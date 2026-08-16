"""Canonical projections for the provisional M06-02 representation spine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=False)
    return dict(value)


def _sorted(values: tuple[Any, ...] | list[Any]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_lineage(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document["input_digests"] = sorted(document["input_digests"])
    document["output_feature_ids"] = sorted(document["output_feature_ids"])
    document["evidence"] = _sorted(document["evidence"])
    return document


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document["source_artifacts"] = _sorted(document["source_artifacts"])
    document["features"] = _sorted(document["features"])
    document["lineage"] = _sorted(
        [normalized_lineage(item) for item in document["lineage"]]
    )
    document["masks"] = _sorted(document["masks"])
    document["covariates"] = _sorted(document["covariates"])
    return document


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    document["features"] = _sorted(document["features"])
    document["lineage"] = _sorted(
        [normalized_lineage(item) for item in document["lineage"]]
    )
    document["masks"] = _sorted(document["masks"])
    document["evidence"] = _sorted(document["evidence"])
    document["limitations"] = _sorted(document["limitations"])
    document["provenance"]["input_digests"] = sorted(
        document["provenance"]["input_digests"]
    )
    document["provenance"]["control_decisions"] = _sorted(
        document["provenance"]["control_decisions"]
    )
    return document


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "normalized_lineage",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
]
