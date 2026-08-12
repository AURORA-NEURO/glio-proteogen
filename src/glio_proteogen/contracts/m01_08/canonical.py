"""Semantic canonicalization for M01-08 release packaging."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    return policy.model_dump(mode="python", by_alias=True, exclude_none=False)


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    for field in (
        "artifacts",
        "software_versions",
        "reference_versions",
        "transformations",
        "decisions",
        "numerical_tolerances",
    ):
        value[field] = _sort(value[field])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def configuration_digest(policy: BaseModel) -> Sha256Digest:
    return policy_digest(policy)


def manifest_digest(manifest: BaseModel) -> Sha256Digest:
    value = manifest.model_dump(mode="python", by_alias=True, exclude_none=False)
    for field in (
        "artifacts",
        "software_versions",
        "reference_versions",
        "transformations",
        "decisions",
        "numerical_tolerances",
    ):
        value[field] = _sort(value[field])
    return sha256_digest(value)


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    value["evidence"] = _sort(value["evidence"])
    value["limitations"] = _sort(value["limitations"])
    value["provenance"]["input_digests"] = _sort(
        value["provenance"]["input_digests"]
    )
    value["provenance"]["control_decisions"] = _sort(
        value["provenance"]["control_decisions"]
    )
    return value


def result_payload_digest(result: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(result))


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "manifest_digest",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "result_payload_digest",
]
