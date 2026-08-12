"""Semantic canonicalization for M01-04 quality metric computation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_assay_profile(profile: BaseModel) -> dict[str, Any]:
    value = profile.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["required_metric_ids"] = _sort(value["required_metric_ids"])
    return value


def profile_digest(profile: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_assay_profile(profile))


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    value = policy.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["enabled_categories"] = _sort(value["enabled_categories"])
    return value


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def normalized_metric_definition(definition: BaseModel) -> dict[str, Any]:
    value = definition.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["observation_ids"] = list(value["observation_ids"])
    return value


def metric_definition_digest(definition: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_metric_definition(definition))


def observation_digest(observation: BaseModel) -> Sha256Digest:
    value = observation.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["evidence"] = _sort(value["evidence"])
    return sha256_digest(value)


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["assay_profile"]["required_metric_ids"] = _sort(
        value["assay_profile"]["required_metric_ids"]
    )
    value["policy"]["enabled_categories"] = _sort(
        value["policy"]["enabled_categories"]
    )
    value["metric_definitions"] = _sort(value["metric_definitions"])
    for observation in value["observations"]:
        observation["evidence"] = _sort(observation["evidence"])
    value["observations"] = _sort(value["observations"])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    for metric in value["metrics"]:
        metric["evidence"] = _sort(metric["evidence"])
    value["metrics"] = _sort(value["metrics"])
    value["provenance"]["input_digests"] = _sort(
        value["provenance"]["input_digests"]
    )
    value["provenance"]["control_decisions"] = _sort(
        value["provenance"]["control_decisions"]
    )
    value["evidence"] = _sort(value["evidence"])
    value["limitations"] = _sort(value["limitations"])
    return value


def result_payload_digest(result: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(result))


__all__ = [
    "canonical_request_digest",
    "metric_definition_digest",
    "normalized_assay_profile",
    "normalized_metric_definition",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "observation_digest",
    "policy_digest",
    "profile_digest",
    "result_payload_digest",
]
