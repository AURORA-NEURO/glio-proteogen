"""Semantic canonicalization for M02-02 identity-binding reconciliation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    value = policy.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["allowed_entity_kinds"] = _sort(value["allowed_entity_kinds"])
    value["allowed_token_scope_ids"] = _sort(value["allowed_token_scope_ids"])
    return value


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def identity_resolution_reference(resolution: BaseModel) -> dict[str, Any]:
    value = resolution.model_dump(mode="python", by_alias=True, exclude_none=False)
    return {
        "resolution_id": value["resolution_id"],
        "resolution_version": value["resolution_version"],
        "resolution_digest": value["resolution_digest"],
        "core_digest": value["core_digest"],
        "decision": value["decision"],
        "graph_digest": value["graph"]["graph_digest"],
    }


def configuration_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest({"policy": normalized_policy(policy)})


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    policy = value["policy"]
    policy["allowed_entity_kinds"] = _sort(policy["allowed_entity_kinds"])
    policy["allowed_token_scope_ids"] = _sort(policy["allowed_token_scope_ids"])
    resolution = value["identity_resolution"]
    value["identity_resolution"] = {
        "resolution_id": resolution["resolution_id"],
        "resolution_version": resolution["resolution_version"],
        "resolution_digest": resolution["resolution_digest"],
        "core_digest": resolution["core_digest"],
        "decision": resolution["decision"],
        "graph_digest": resolution["graph"]["graph_digest"],
    }
    for binding in value["bindings"]:
        binding["observed_subject_component_ids"] = _sort(
            binding["observed_subject_component_ids"]
        )
        binding["evidence"] = _sort(binding["evidence"])
    value["bindings"] = _sort(value["bindings"])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    for binding in value["bindings"]:
        binding["upstream_subject_component_ids"] = _sort(
            binding["upstream_subject_component_ids"]
        )
        binding["observed_subject_component_ids"] = _sort(
            binding["observed_subject_component_ids"]
        )
        binding["finding_codes"] = _sort(binding["finding_codes"])
    for finding in value["findings"]:
        finding["binding_ids"] = _sort(finding["binding_ids"])
        finding["artifact_digests"] = _sort(finding["artifact_digests"])
        finding["component_ids"] = _sort(finding["component_ids"])
    value["bindings"] = _sort(value["bindings"])
    value["findings"] = _sort(value["findings"])
    value["evidence"] = _sort(value["evidence"])
    value["limitations"] = _sort(value["limitations"])
    value["lineage_graph"]["nodes"] = _sort(value["lineage_graph"]["nodes"])
    value["lineage_graph"]["operations"] = _sort(
        value["lineage_graph"]["operations"]
    )
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
    "identity_resolution_reference",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "result_payload_digest",
]
