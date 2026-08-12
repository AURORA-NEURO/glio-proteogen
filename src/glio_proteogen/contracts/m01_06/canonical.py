"""Semantic canonicalization for deterministic M01-06 harmonization."""

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
    for stage in value["stages"]:
        stage["control_sample_ids"] = _sort(stage["control_sample_ids"])
        stage["control_feature_ids"] = _sort(stage["control_feature_ids"])
    return value


def profile_digest(profile: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_profile(profile))


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(policy.model_dump(mode="python", by_alias=True, exclude_none=False))


def normalized_observation(observation: BaseModel) -> dict[str, Any]:
    value = observation.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["factor_levels"] = _sort(value["factor_levels"])
    value["evidence"] = _sort(value["evidence"])
    return value


def observation_digest(observation: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_observation(observation))


def normalized_invariant(invariant: BaseModel) -> dict[str, Any]:
    return invariant.model_dump(mode="python", by_alias=True, exclude_none=False)


def invariant_digest(invariant: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_invariant(invariant))


def configuration_digest(
    profile: BaseModel,
    policy: BaseModel,
    invariants: tuple[BaseModel, ...],
) -> Sha256Digest:
    return sha256_digest(
        {
            "profile": normalized_profile(profile),
            "policy": policy.model_dump(mode="python", by_alias=True, exclude_none=False),
            "biological_invariants": _sort(
                [normalized_invariant(invariant) for invariant in invariants]
            ),
        }
    )


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    for stage in value["profile"]["stages"]:
        stage["control_sample_ids"] = _sort(stage["control_sample_ids"])
        stage["control_feature_ids"] = _sort(stage["control_feature_ids"])
    for observation in value["observations"]:
        observation["factor_levels"] = _sort(observation["factor_levels"])
        observation["evidence"] = _sort(observation["evidence"])
    value["observations"] = _sort(value["observations"])
    value["biological_invariants"] = _sort(value["biological_invariants"])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    value["values"] = _sort(value["values"])
    for stage in value["transformation_manifest"]["stages"]:
        stage["level_shifts"] = _sort(stage["level_shifts"])
    value["technical_effect_diagnostics"] = _sort(value["technical_effect_diagnostics"])
    value["biological_invariant_diagnostics"] = _sort(
        value["biological_invariant_diagnostics"]
    )
    value["provenance"]["input_digests"] = _sort(value["provenance"]["input_digests"])
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
    "invariant_digest",
    "normalized_invariant",
    "normalized_observation",
    "normalized_profile",
    "normalized_request",
    "normalized_result_payload",
    "observation_digest",
    "policy_digest",
    "profile_digest",
    "result_payload_digest",
]
