"""Semantic canonicalization for M02-05 identification-artifact detection."""

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


def normalized_signal(signal: BaseModel) -> dict[str, Any]:
    value = signal.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["evidence"] = _sort(value["evidence"])
    return value


def signal_digest(signal: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_signal(signal))


def signal_summary_digest(
    signal: BaseModel,
    *,
    target_id: str | None = None,
) -> Sha256Digest:
    value = normalized_signal(signal)
    return signal_summary_digest_from_values(
        (
            target_id or value["target_id"],
            value["signal_id"],
            value["state"],
            value["value"],
            value["unit"],
        ),
        tuple(reference["digest"] for reference in value["evidence"]),
    )


def signal_summary_digest_from_values(
    summary: tuple[str, str, str, float | bool | None, str | None],
    evidence_digests: tuple[str, ...],
) -> Sha256Digest:
    target_id, signal_id, state, value, unit = summary
    return sha256_digest(
        {
            "target_id": target_id,
            "signal_id": signal_id,
            "state": state,
            "value": value,
            "unit": unit,
            "evidence_digests": _sort(evidence_digests),
        }
    )


def configuration_digest(
    profile: BaseModel,
    policy: BaseModel,
    rules: tuple[BaseModel, ...],
) -> Sha256Digest:
    return configuration_manifest_digest(
        profile_digest(profile),
        policy_digest(policy),
        tuple(rule_digest(rule) for rule in rules),
    )


def configuration_manifest_digest(
    active_profile_digest: Sha256Digest,
    active_policy_digest: Sha256Digest,
    rule_digests: tuple[Sha256Digest, ...],
) -> Sha256Digest:
    return sha256_digest(
        {
            "profile_digest": active_profile_digest,
            "policy_digest": active_policy_digest,
            "rule_digests": _sort(rule_digests),
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
    value["required_rule_ids"] = _sort(value["required_rule_ids"])
    value["enabled_classes"] = _sort(value["enabled_classes"])
    value["evaluated_target_ids"] = _sort(value["evaluated_target_ids"])
    for flag in value["flags"]:
        flag["rule_ids"] = _sort(flag["rule_ids"])
        for evaluation in flag["evaluations"]:
            evaluation["evidence_digests"] = _sort(evaluation["evidence_digests"])
        flag["evaluations"] = _sort(flag["evaluations"])
        flag["provenance"]["rule_digests"] = _sort(
            flag["provenance"]["rule_digests"]
        )
        flag["provenance"]["signal_digests"] = _sort(
            flag["provenance"]["signal_digests"]
        )
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
    "configuration_manifest_digest",
    "normalized_policy",
    "normalized_profile",
    "normalized_request",
    "normalized_result_payload",
    "normalized_signal",
    "policy_digest",
    "profile_digest",
    "result_payload_digest",
    "rule_digest",
    "signal_digest",
    "signal_summary_digest",
    "signal_summary_digest_from_values",
]
