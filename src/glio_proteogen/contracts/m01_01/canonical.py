"""Semantic canonicalization shared by M01-01 contracts, services, and ledgers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _canonical_sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    """Return a stable ordering without collapsing meaningful multiplicity."""

    return sorted(values, key=canonical_json_bytes)


def normalized_protocol(schema: BaseModel) -> dict[str, Any]:
    """Normalize collections whose order has no meaning in the M01-01 contract."""

    normalized = schema.model_dump(mode="python", by_alias=True, exclude_none=False)
    return _normalized_protocol_mapping(normalized)


def _normalized_protocol_mapping(normalized: dict[str, Any]) -> dict[str, Any]:
    normalized["assay_versions"] = _canonical_sort(normalized["assay_versions"])
    normalized["specimen_versions"] = _canonical_sort(normalized["specimen_versions"])

    for field in normalized["fields"]:
        field["allowed_units"] = _canonical_sort(field["allowed_units"])
        field["allowed_missingness"] = _canonical_sort(field["allowed_missingness"])
    normalized["fields"] = _canonical_sort(normalized["fields"])

    for vocabulary in normalized["vocabularies"]:
        vocabulary["terms"] = _canonical_sort(vocabulary["terms"])
    normalized["vocabularies"] = _canonical_sort(normalized["vocabularies"])
    normalized["units"] = _canonical_sort(normalized["units"])

    for rule in normalized["compatibility_rules"]:
        for predicate_group in ("when_all", "require_all"):
            for predicate in rule[predicate_group]:
                predicate["values"] = _canonical_sort(predicate["values"])
            rule[predicate_group] = _canonical_sort(rule[predicate_group])
    normalized["compatibility_rules"] = _canonical_sort(normalized["compatibility_rules"])
    normalized["limitations"] = _canonical_sort(normalized["limitations"])
    return normalized


def normalized_document(document: BaseModel) -> dict[str, Any]:
    """Normalize entry and value order while retaining duplicate-value cardinality."""

    normalized = document.model_dump(mode="python", by_alias=True, exclude_none=False)
    return _normalized_document_mapping(normalized)


def _normalized_document_mapping(normalized: dict[str, Any]) -> dict[str, Any]:
    for entry in normalized["entries"]:
        entry["values"] = _canonical_sort(entry["values"])
    normalized["entries"] = _canonical_sort(normalized["entries"])
    return normalized


def canonical_protocol_bytes(schema: BaseModel) -> bytes:
    """Return the sole canonical byte representation for an M01-01 protocol."""

    return canonical_json_bytes(normalized_protocol(schema))


def protocol_digest(schema: BaseModel) -> Sha256Digest:
    """Hash an M01-01 protocol after domain-specific semantic normalization."""

    return sha256_digest(normalized_protocol(schema))


def metadata_document_digest(document: BaseModel) -> Sha256Digest:
    """Hash metadata after normalizing semantically unordered entries and values."""

    return sha256_digest(normalized_document(document))


def identity_binding_digest(schema: BaseModel, document: BaseModel) -> Sha256Digest:
    """Hash only declared identity-key evidence for lineage reconciliation."""

    schema_value = schema.model_dump(mode="python", by_alias=True, exclude_none=False)
    document_value = document.model_dump(mode="python", by_alias=True, exclude_none=False)
    identity_paths = sorted(
        field["path"] for field in schema_value["fields"] if field["identity_key"] is True
    )
    entries = {entry["path"]: entry for entry in document_value["entries"]}
    binding = {
        "schema_id": schema_value["schema_id"],
        "schema_version": schema_value["version"],
        "identity_entries": [
            {
                "path": path,
                "values": _canonical_sort(entries[path]["values"]) if path in entries else [],
            }
            for path in identity_paths
        ],
    }
    return sha256_digest(binding)


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    """Hash a request using the same protocol/document identity rules as persistence."""

    normalized = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    operation = normalized.get("operation")
    if operation == "register":
        normalized["protocol_schema"] = _normalized_protocol_mapping(normalized["protocol_schema"])
    elif operation == "evaluate":
        normalized["document"] = _normalized_document_mapping(normalized["document"])
    else:
        raise ValueError("canonical M01-01 request has an unsupported operation")
    return sha256_digest(normalized)


__all__ = [
    "canonical_protocol_bytes",
    "canonical_request_digest",
    "identity_binding_digest",
    "metadata_document_digest",
    "normalized_document",
    "normalized_protocol",
    "protocol_digest",
]
