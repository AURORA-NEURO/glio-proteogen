"""Semantic canonicalization for M01-07 support routing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_profile(profile: BaseModel) -> dict[str, Any]:
    value = profile.model_dump(mode="python", by_alias=True, exclude_none=False)
    for criterion in value["criteria"]:
        criterion["allowed_terms"] = _sort(criterion["allowed_terms"])
    value["criteria"] = _sort(value["criteria"])
    return value


def profile_digest(profile: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_profile(profile))


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    return policy.model_dump(mode="python", by_alias=True, exclude_none=False)


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def configuration_digest(profile: BaseModel, policy: BaseModel) -> Sha256Digest:
    return sha256_digest(
        {"profile": normalized_profile(profile), "policy": normalized_policy(policy)}
    )


def evidence_digest(evidence: BaseModel) -> Sha256Digest:
    value = evidence.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["evidence"] = _sort(value["evidence"])
    return sha256_digest(value)


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    for criterion in value["profile"]["criteria"]:
        criterion["allowed_terms"] = _sort(criterion["allowed_terms"])
    value["profile"]["criteria"] = _sort(value["profile"]["criteria"])
    for item in value["evidence"]:
        item["evidence"] = _sort(item["evidence"])
    value["evidence"] = _sort(value["evidence"])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    for assessment in value["assessments"]:
        assessment["evidence_digests"] = _sort(assessment["evidence_digests"])
    value["assessments"] = _sort(value["assessments"])
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
    "configuration_digest",
    "evidence_digest",
    "normalized_policy",
    "normalized_profile",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "profile_digest",
    "result_payload_digest",
]
