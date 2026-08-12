"""Semantic canonicalization for M02-06 identification harmonization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


class _PrerequisitesLike(Protocol):
    conformance: BaseModel
    identity: BaseModel
    ingestion: BaseModel
    quality: BaseModel
    artifact_detection: _ArtifactDetectionLike


class _ExclusionMaskLike(Protocol):
    excluded_target_ids: tuple[str, ...]
    review_target_ids: tuple[str, ...]


class _ArtifactDetectionLike(Protocol):
    result_digest: str
    disposition: Any
    evaluated_target_ids: tuple[str, ...]
    exclusion_mask: _ExclusionMaskLike


class _RequestLike(Protocol):
    operation: str
    contract_version: str
    context: BaseModel
    prerequisites: _PrerequisitesLike
    profile: BaseModel
    policy: BaseModel
    observations: tuple[BaseModel, ...]
    biological_controls: tuple[BaseModel, ...]
    supersedes_result_digest: str | None


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_observation(observation: BaseModel) -> dict[str, Any]:
    value = observation.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["factor_levels"] = _sort(value["factor_levels"])
    value["evidence"] = _sort(value["evidence"])
    return value


def observation_digest(observation: BaseModel) -> Sha256Digest:
    value = normalized_observation(observation)
    return observation_summary_digest(
        target_id=value["target_id"],
        feature_id=value["feature_id"],
        biological_group_id=value["biological_group_id"],
        state=value["state"],
        value=value["value"],
        censoring_limit=value["censoring_limit"],
        unit=value["unit"],
        factor_levels=tuple((item["factor"], item["level_id"]) for item in value["factor_levels"]),
        evidence_digests=tuple(item["digest"] for item in value["evidence"]),
    )


def observation_summary_digest(  # noqa: PLR0913 - exact closed observation manifest.
    *,
    target_id: str,
    feature_id: str,
    biological_group_id: str,
    state: str,
    value: float | None,
    censoring_limit: float | None,
    unit: str,
    factor_levels: tuple[tuple[str, str], ...],
    evidence_digests: tuple[str, ...],
) -> Sha256Digest:
    return sha256_digest(
        {
            "target_id": target_id,
            "feature_id": feature_id,
            "biological_group_id": biological_group_id,
            "state": state,
            "value": value,
            "censoring_limit": censoring_limit,
            "unit": unit,
            "factor_levels": _sort(factor_levels),
            "evidence_digests": _sort(evidence_digests),
        }
    )


def normalized_profile(profile: BaseModel) -> dict[str, Any]:
    value = profile.model_dump(mode="python", by_alias=True, exclude_none=False)
    for stage in value["stages"]:
        stage["control_target_ids"] = _sort(stage["control_target_ids"])
        stage["control_feature_ids"] = _sort(stage["control_feature_ids"])
    return value


def profile_digest(profile: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_profile(profile))


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(policy.model_dump(mode="python", by_alias=True, exclude_none=False))


def invariant_digest(invariant: BaseModel) -> Sha256Digest:
    value = invariant.model_dump(mode="python", by_alias=True, exclude_none=False)
    return sha256_digest(value)


def context_digest(context: BaseModel) -> Sha256Digest:
    """Bind the immutable execution context without copying it into the result."""

    return sha256_digest(context.model_dump(mode="python", by_alias=True, exclude_none=False))


def _issued_result_digest(result: object) -> str:
    for name in ("evaluation_digest", "result_digest"):
        value = getattr(result, name, None)
        if isinstance(value, str):
            return value
    raise ValueError("upstream result does not expose an issued digest")


def _issued_disposition(result: object) -> str:
    disposition = getattr(result, "disposition", None)
    value = getattr(disposition, "value", None)
    if not isinstance(value, str):
        raise TypeError("upstream result does not expose a disposition")
    return value


def normalized_prerequisites(prerequisites: _PrerequisitesLike) -> list[dict[str, Any]]:
    """Reduce exact validated upstream results to their immutable public receipts."""

    modules = (
        ("GLIO-PROTEOGEN-M02-01", prerequisites.conformance),
        ("GLIO-PROTEOGEN-M02-02", prerequisites.identity),
        ("GLIO-PROTEOGEN-M02-03", prerequisites.ingestion),
        ("GLIO-PROTEOGEN-M02-04", prerequisites.quality),
        ("GLIO-PROTEOGEN-M02-05", prerequisites.artifact_detection),
    )
    receipts: list[dict[str, Any]] = []
    for module_id, result in modules:
        receipt: dict[str, Any] = {
            "module_id": module_id,
            "result_digest": _issued_result_digest(result),
            "disposition": _issued_disposition(result),
        }
        if module_id == "GLIO-PROTEOGEN-M02-05":
            artifact = prerequisites.artifact_detection
            receipt["evaluated_target_ids"] = sorted(artifact.evaluated_target_ids)
            receipt["excluded_target_ids"] = sorted(artifact.exclusion_mask.excluded_target_ids)
            receipt["review_target_ids"] = sorted(artifact.exclusion_mask.review_target_ids)
        receipts.append(receipt)
    return receipts


def prerequisites_digest(prerequisites: _PrerequisitesLike) -> Sha256Digest:
    return sha256_digest(normalized_prerequisites(prerequisites))


def request_manifest_digest(  # noqa: PLR0913 - exact closed request manifest.
    *,
    active_context_digest: str,
    active_prerequisites_digest: str,
    active_profile_digest: str,
    active_policy_digest: str,
    observation_digests: tuple[str, ...],
    invariant_digests: tuple[str, ...],
    supersedes_result_digest: str | None,
) -> Sha256Digest:
    """Hash the exact privacy-safe request manifest used by request and result."""

    return sha256_digest(
        {
            "operation": "harmonize_identification_evidence",
            "contract_version": "1.0.0",
            "context_digest": active_context_digest,
            "prerequisites_digest": active_prerequisites_digest,
            "profile_digest": active_profile_digest,
            "policy_digest": active_policy_digest,
            "observation_digests": _sort(observation_digests),
            "invariant_digests": _sort(invariant_digests),
            "supersedes_result_digest": supersedes_result_digest,
        }
    )


def configuration_digest(
    profile: BaseModel,
    policy: BaseModel,
    invariants: tuple[BaseModel, ...],
) -> Sha256Digest:
    return configuration_manifest_digest(
        profile_digest(profile),
        policy_digest(policy),
        tuple(invariant_digest(item) for item in invariants),
    )


def configuration_manifest_digest(
    active_profile_digest: str,
    active_policy_digest: str,
    invariant_digests: tuple[str, ...],
) -> Sha256Digest:
    return sha256_digest(
        {
            "profile_digest": active_profile_digest,
            "policy_digest": active_policy_digest,
            "invariant_digests": _sort(invariant_digests),
        }
    )


def normalized_request(request: _RequestLike) -> dict[str, Any]:
    return {
        "operation": request.operation,
        "contract_version": request.contract_version,
        "context_digest": context_digest(request.context),
        "prerequisites_digest": prerequisites_digest(request.prerequisites),
        "profile_digest": profile_digest(request.profile),
        "policy_digest": policy_digest(request.policy),
        "observation_digests": _sort([observation_digest(item) for item in request.observations]),
        "invariant_digests": _sort(
            [invariant_digest(item) for item in request.biological_controls]
        ),
        "supersedes_result_digest": request.supersedes_result_digest,
    }


def canonical_request_digest(request: _RequestLike) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    for stage in value["profile"]["stages"]:
        stage["control_target_ids"] = _sort(stage["control_target_ids"])
        stage["control_feature_ids"] = _sort(stage["control_feature_ids"])
    for item in value["values"]:
        item["source_observation"]["factor_levels"] = _sort(
            item["source_observation"]["factor_levels"]
        )
        item["source_observation"]["evidence_digests"] = _sort(
            item["source_observation"]["evidence_digests"]
        )
    value["values"] = _sort(value["values"])
    value["biological_controls"] = _sort(value["biological_controls"])
    for receipt in value["upstream_receipts"]:
        receipt["evaluated_target_ids"] = _sort(receipt["evaluated_target_ids"])
        receipt["excluded_target_ids"] = _sort(receipt["excluded_target_ids"])
        receipt["review_target_ids"] = _sort(receipt["review_target_ids"])
    value["biological_invariant_diagnostics"] = _sort(value["biological_invariant_diagnostics"])
    value["upstream_receipts"] = _sort(value["upstream_receipts"])
    for stage in value["transformation_manifest"]["stages"]:
        stage["control_target_ids"] = _sort(stage["control_target_ids"])
        stage["control_feature_ids"] = _sort(stage["control_feature_ids"])
        stage["level_shifts"] = _sort(stage["level_shifts"])
    value["technical_effect_diagnostics"] = _sort(value["technical_effect_diagnostics"])
    value["provenance"]["input_digests"] = _sort(value["provenance"]["input_digests"])
    value["provenance"]["control_decisions"] = _sort(value["provenance"]["control_decisions"])
    value["evidence"] = _sort(value["evidence"])
    value["limitations"] = _sort(value["limitations"])
    return value


def result_payload_digest(result: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(result))


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "configuration_manifest_digest",
    "context_digest",
    "invariant_digest",
    "normalized_observation",
    "normalized_prerequisites",
    "normalized_profile",
    "normalized_request",
    "normalized_result_payload",
    "observation_digest",
    "observation_summary_digest",
    "policy_digest",
    "prerequisites_digest",
    "profile_digest",
    "request_manifest_digest",
    "result_payload_digest",
]
