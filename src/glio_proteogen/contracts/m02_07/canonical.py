"""Semantic canonicalization for M02-07 joint support-envelope routing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


class _RequestLike(Protocol):
    operation: str
    contract_version: str
    context: BaseModel
    prerequisites: BaseModel
    profile: BaseModel
    policy: BaseModel
    declared_facts: tuple[BaseModel, ...]
    context_receipts: tuple[BaseModel, ...]
    supersedes_result_digest: str | None


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_fact(fact: BaseModel) -> dict[str, Any]:
    value = fact.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["values"] = sorted(value["values"])
    value["evidence"] = _sort(value["evidence"])
    return value


def fact_digest(fact: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_fact(fact))


def normalized_context_receipt(receipt: BaseModel) -> dict[str, Any]:
    return receipt.model_dump(mode="python", by_alias=True, exclude_none=False)


def context_receipt_digest(receipt: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_context_receipt(receipt))


def normalized_profile(profile: BaseModel) -> dict[str, Any]:
    value = profile.model_dump(mode="python", by_alias=True, exclude_none=False)
    for envelope in value["envelopes"]:
        for field in (
            "assay_types",
            "specimen_terms",
            "disease_class_terms",
            "quality_statuses",
            "platform_ids",
            "reference_ids",
            "intended_use_terms",
            "required_context_roles",
        ):
            envelope[field] = sorted(envelope[field])
        envelope["remediations"] = _sort(envelope["remediations"])
    value["envelopes"] = _sort(value["envelopes"])
    return value


def profile_digest(profile: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_profile(profile))


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(policy.model_dump(mode="python", by_alias=True, exclude_none=False))


def normalized_prerequisites(prerequisites: BaseModel) -> dict[str, Any]:
    value = prerequisites.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["quality"]["metric_statuses"] = sorted(value["quality"]["metric_statuses"])
    value["harmonization"]["platform_ids"] = sorted(value["harmonization"]["platform_ids"])
    return value


def prerequisites_digest(prerequisites: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_prerequisites(prerequisites))


def context_digest(context: BaseModel) -> Sha256Digest:
    return sha256_digest(context.model_dump(mode="python", by_alias=True, exclude_none=False))


def configuration_manifest_digest(
    active_profile_digest: str,
    active_policy_digest: str,
) -> Sha256Digest:
    return sha256_digest(
        {
            "profile_digest": active_profile_digest,
            "policy_digest": active_policy_digest,
        }
    )


def configuration_digest(profile: BaseModel, policy: BaseModel) -> Sha256Digest:
    return configuration_manifest_digest(profile_digest(profile), policy_digest(policy))


def request_manifest_digest(  # noqa: PLR0913 - exact closed request receipt.
    *,
    active_context_digest: str,
    active_prerequisites_digest: str,
    active_profile_digest: str,
    active_policy_digest: str,
    fact_digests: tuple[str, ...],
    context_receipt_digests: tuple[str, ...],
    supersedes_result_digest: str | None,
) -> Sha256Digest:
    return sha256_digest(
        {
            "operation": "route_identification_support",
            "contract_version": "1.0.0",
            "context_digest": active_context_digest,
            "prerequisites_digest": active_prerequisites_digest,
            "profile_digest": active_profile_digest,
            "policy_digest": active_policy_digest,
            "fact_digests": sorted(fact_digests),
            "context_receipt_digests": sorted(context_receipt_digests),
            "supersedes_result_digest": supersedes_result_digest,
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
        "fact_digests": sorted(fact_digest(item) for item in request.declared_facts),
        "context_receipt_digests": sorted(
            context_receipt_digest(item) for item in request.context_receipts
        ),
        "supersedes_result_digest": request.supersedes_result_digest,
    }


def canonical_request_digest(request: _RequestLike) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    value["prerequisites"]["quality"]["metric_statuses"] = sorted(
        value["prerequisites"]["quality"]["metric_statuses"]
    )
    value["prerequisites"]["harmonization"]["platform_ids"] = sorted(
        value["prerequisites"]["harmonization"]["platform_ids"]
    )
    for envelope in value["profile"]["envelopes"]:
        for field in (
            "assay_types",
            "specimen_terms",
            "disease_class_terms",
            "quality_statuses",
            "platform_ids",
            "reference_ids",
            "intended_use_terms",
            "required_context_roles",
        ):
            envelope[field] = sorted(envelope[field])
        envelope["remediations"] = _sort(envelope["remediations"])
    value["profile"]["envelopes"] = _sort(value["profile"]["envelopes"])
    for fact in value["declared_facts"]:
        fact["values"] = sorted(fact["values"])
        fact["evidence"] = _sort(fact["evidence"])
    value["declared_facts"] = _sort(value["declared_facts"])
    value["context_receipts"] = _sort(value["context_receipts"])
    value["matched_envelope_ids"] = sorted(value["matched_envelope_ids"])
    for assessment in value["envelope_assessments"]:
        assessment["dimensions"] = _sort(assessment["dimensions"])
    value["envelope_assessments"] = _sort(value["envelope_assessments"])
    value["abstention_reasons"] = _sort(value["abstention_reasons"])
    value["provenance"]["input_digests"] = sorted(value["provenance"]["input_digests"])
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
    "context_receipt_digest",
    "fact_digest",
    "normalized_context_receipt",
    "normalized_fact",
    "normalized_prerequisites",
    "normalized_profile",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "prerequisites_digest",
    "profile_digest",
    "request_manifest_digest",
    "result_payload_digest",
]
