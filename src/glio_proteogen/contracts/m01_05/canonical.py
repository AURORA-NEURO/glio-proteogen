"""Semantic canonicalization for M01-05 artifact detection."""

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
    value["required_rule_ids"] = _sort(value["required_rule_ids"])
    return value


def profile_digest(profile: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_profile(profile))


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    value = policy.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["enabled_classes"] = _sort(value["enabled_classes"])
    return value


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def rule_digest(rule: BaseModel) -> Sha256Digest:
    return sha256_digest(rule.model_dump(mode="python", by_alias=True, exclude_none=False))


def signal_digest(signal: BaseModel) -> Sha256Digest:
    value = signal.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["evidence"] = _sort(value["evidence"])
    return sha256_digest(value)


def configuration_digest(
    profile: BaseModel,
    policy: BaseModel,
    rules: tuple[BaseModel, ...],
) -> Sha256Digest:
    return sha256_digest(
        {
            "profile": normalized_profile(profile),
            "policy": normalized_policy(policy),
            "rules": _sort(
                [
                    rule.model_dump(mode="python", by_alias=True, exclude_none=False)
                    for rule in rules
                ]
            ),
        }
    )


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["detector_profile"]["required_rule_ids"] = _sort(
        value["detector_profile"]["required_rule_ids"]
    )
    value["policy"]["enabled_classes"] = _sort(value["policy"]["enabled_classes"])
    value["rules"] = _sort(value["rules"])
    for signal in value["signals"]:
        signal["evidence"] = _sort(signal["evidence"])
    value["signals"] = _sort(value["signals"])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    for flag in value["flags"]:
        flag["rule_ids"] = _sort(flag["rule_ids"])
        flag["provenance"]["rule_digests"] = _sort(flag["provenance"]["rule_digests"])
        flag["provenance"]["signal_digests"] = _sort(flag["provenance"]["signal_digests"])
        flag["evidence"] = _sort(flag["evidence"])
    value["flags"] = _sort(value["flags"])
    value["exclusion_mask"]["excluded_target_ids"] = _sort(
        value["exclusion_mask"]["excluded_target_ids"]
    )
    value["exclusion_mask"]["review_target_ids"] = _sort(
        value["exclusion_mask"]["review_target_ids"]
    )
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
    "normalized_policy",
    "normalized_profile",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "profile_digest",
    "result_payload_digest",
    "rule_digest",
    "signal_digest",
]
