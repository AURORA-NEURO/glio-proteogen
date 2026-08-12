"""Semantic canonicalization for M02-03 identification raw-input ingestion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def _normalize_base_policy(value: dict[str, Any]) -> None:
    value["allowed_formats"] = _sort(value["allowed_formats"])
    value["allowed_compressions"] = _sort(value["allowed_compressions"])


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    value = policy.model_dump(mode="python", by_alias=True, exclude_none=False)
    _normalize_base_policy(value["base_policy"])
    for requirement in value["role_requirements"]:
        requirement["allowed_formats"] = _sort(requirement["allowed_formats"])
    value["role_requirements"] = _sort(value["role_requirements"])
    return value


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def configuration_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest({"identification_ingestion_policy": normalized_policy(policy)})


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    policy = value["policy"]
    _normalize_base_policy(policy["base_policy"])
    for requirement in policy["role_requirements"]:
        requirement["allowed_formats"] = _sort(requirement["allowed_formats"])
    policy["role_requirements"] = _sort(policy["role_requirements"])
    value["sources"] = _sort(value["sources"])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    for item in value["raw_inputs"]:
        raw_input = item["raw_input"]
        for diagnostic in raw_input["diagnostics"]:
            diagnostic["evidence"] = _sort(diagnostic["evidence"])
        raw_input["diagnostics"] = _sort(raw_input["diagnostics"])
    for diagnostic in value["bundle_diagnostics"]:
        diagnostic["source_ids"] = _sort(diagnostic["source_ids"])
    value["raw_inputs"] = _sort(value["raw_inputs"])
    value["bundle_diagnostics"] = _sort(value["bundle_diagnostics"])
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
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "result_payload_digest",
]
