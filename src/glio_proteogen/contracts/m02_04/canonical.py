"""Semantic canonicalization for M02-04 identification quality computation."""

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
    value["thresholds"] = _sort(value["thresholds"])
    return value


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def configuration_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest({"identification_quality_policy": normalized_policy(policy)})


def assay_profile_digest(profile: BaseModel) -> Sha256Digest:
    return sha256_digest(profile)


def observation_digest(observation: BaseModel) -> Sha256Digest:
    value = observation.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["evidence"] = _sort(value["evidence"])
    return sha256_digest(value)


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["policy"]["thresholds"] = _sort(value["policy"]["thresholds"])
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
        metric["observation"]["evidence"] = _sort(
            metric["observation"]["evidence"]
        )
    value["metrics"] = _sort(value["metrics"])
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
    "assay_profile_digest",
    "canonical_request_digest",
    "configuration_digest",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "observation_digest",
    "policy_digest",
    "result_payload_digest",
]
