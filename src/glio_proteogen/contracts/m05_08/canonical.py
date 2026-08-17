"""Canonical projections for the provisional M05-08 package spine."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    return value.model_dump(mode="python", by_alias=True, exclude_none=False)


def _sorted(value: tuple[Any, ...] | list[Any]) -> list[Any]:
    return sorted(value, key=canonical_json_bytes)


def normalized_manifest(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    for name in (
        "artifact_digests",
        "stage_result_digests",
        "software_versions",
        "reference_versions",
        "transformation_digests",
        "quality_decision_ids",
        "reproducibility_evidence",
        "transformations",
        "quality_decisions",
    ):
        if name in document:
            document[name] = _sorted(document[name])
    return document


def manifest_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_manifest(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document["allowed_signature_algorithms"] = sorted(document["allowed_signature_algorithms"])
    document["allowed_verifier_ids"] = sorted(document["allowed_verifier_ids"])
    return document


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document["artifacts"] = _sorted(document["artifacts"])
    document["upstream_result_digests"] = sorted(document["upstream_result_digests"])
    document["manifest"] = normalized_manifest(document["manifest"])
    document["policy"] = normalized_policy(document["policy"])
    document["signature"]["claimed_manifest_digest"] = manifest_digest(document["manifest"])
    return document


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    document["evidence"] = _sorted(document["evidence"])
    document["limitations"] = _sorted(document["limitations"])
    document["quarantine_reasons"] = _sorted(document["quarantine_reasons"])
    document["provenance"]["input_digests"] = sorted(document["provenance"]["input_digests"])
    document["provenance"]["control_decisions"] = _sorted(
        document["provenance"]["control_decisions"]
    )
    return document


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


def signing_statement_digest(
    *,
    active_manifest_digest: str,
    active_policy_digest: str,
    release_id: str,
    release_version: str,
) -> Sha256Digest:
    """Domain-separated digest for a future external signature adapter."""

    return sha256_digest(
        {
            "domain": "GLIO-PROTEOGEN-M05-08:ptm-localization-release:provisional",
            "module_id": "GLIO-PROTEOGEN-M05-08",
            "contract_version": "0.1.0-provisional",
            "manifest_digest": active_manifest_digest,
            "policy_digest": active_policy_digest,
            "release_id": release_id,
            "release_version": release_version,
        }
    )


__all__ = [
    "canonical_request_digest",
    "manifest_digest",
    "normalized_manifest",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "result_payload_digest",
    "signing_statement_digest",
]
