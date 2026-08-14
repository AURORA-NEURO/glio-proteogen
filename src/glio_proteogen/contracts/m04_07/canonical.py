"""Semantic canonicalization for M04-07 proteoform support routing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from glio_proteogen.contracts.m04_04 import normalized_result as normalized_m0404_result
from glio_proteogen.contracts.m04_06 import normalized_result as normalized_m0406_result
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest

_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    # Canonical helpers also normalize trusted results, whose embedded request plus
    # assessments may exceed the public request-ingress ceiling.
    decoded = json.loads(canonical_json_bytes(value))
    if not isinstance(decoded, dict):  # pragma: no cover - contract roots are objects.
        raise TypeError("M04-07 canonical object root must be a mapping")
    return decoded


def _sort(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_quality_support_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["metrics"] = _sort(data["metrics"])
    return data


def quality_support_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    data = normalized_quality_support_receipt(value)
    data.pop("receipt_digest", None)
    return sha256_digest(data)


def normalized_harmonization_support_receipt(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    data = _dump(value)
    data["analysis_platform_level_ids"] = tuple(sorted(data["analysis_platform_level_ids"]))
    return data


def harmonization_support_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    data = normalized_harmonization_support_receipt(value)
    data.pop("receipt_digest", None)
    return sha256_digest(data)


def normalized_prerequisites(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    quality_result_digest = data["quality_result"]["result_digest"]
    harmonization_result_digest = data["harmonization_result"]["result_digest"]
    data["quality_result"] = normalized_m0404_result(data["quality_result"])
    data["quality_result"]["result_digest"] = quality_result_digest
    data["harmonization_result"] = normalized_m0406_result(data["harmonization_result"])
    data["harmonization_result"]["result_digest"] = harmonization_result_digest
    data["quality"] = normalized_quality_support_receipt(data["quality"])
    data["harmonization"] = normalized_harmonization_support_receipt(data["harmonization"])
    return data


def prerequisites_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_prerequisites(value))


def normalized_fact(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["values"] = tuple(sorted(data["values"]))
    data["evidence"] = _sort(data["evidence"])
    return data


def fact_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_fact(value))


def normalized_context_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def context_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_context_receipt(value))


def normalized_remediation(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_envelope(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in (
        "applicabilities",
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabulary_ids",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
        "specimen_terms",
        "disease_class_terms",
        "quality_statuses",
        "platform_level_ids",
        "reference_terms",
        "intended_use_terms",
        "required_context_roles",
    ):
        data[field] = tuple(sorted(data[field]))
    data["remediations"] = _sort(data["remediations"])
    return data


def normalized_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["envelopes"] = _sort(tuple(normalized_envelope(item) for item in data["envelopes"]))
    return data


def profile_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_profile(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(
    profile: BaseModel | dict[str, Any], policy: BaseModel | dict[str, Any]
) -> Sha256Digest:
    return sha256_digest(
        {
            "proteoform_support_profile": normalized_profile(profile),
            "proteoform_support_policy": normalized_policy(policy),
        }
    )


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["prerequisites"] = normalized_prerequisites(data["prerequisites"])
    data["profile"] = normalized_profile(data["profile"])
    data["policy"] = normalized_policy(data["policy"])
    data["declared_facts"] = _sort(tuple(normalized_fact(item) for item in data["declared_facts"]))
    data["context_receipts"] = _sort(
        tuple(normalized_context_receipt(item) for item in data["context_receipts"])
    )
    return data


def normalized_dimension_assessment(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["values"] = tuple(sorted(data["values"]))
    return data


def normalized_envelope_assessment(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["dimensions"] = _sort(
        tuple(normalized_dimension_assessment(item) for item in data["dimensions"])
    )
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["result_digest"] = _DIGEST_SENTINEL
    data["request"] = normalized_request(data["request"])
    data["matched_envelope_ids"] = tuple(sorted(data["matched_envelope_ids"]))
    data["envelope_assessments"] = _sort(
        tuple(normalized_envelope_assessment(item) for item in data["envelope_assessments"])
    )
    data["abstention_reasons"] = _sort(data["abstention_reasons"])
    data["provenance"]["input_digests"] = tuple(sorted(data["provenance"]["input_digests"]))
    data["evidence"] = _sort(data["evidence"])
    data["limitations"] = _sort(data["limitations"])
    data["uncertainty"]["sensitivity_notes"] = tuple(
        sorted(data["uncertainty"]["sensitivity_notes"])
    )
    return data


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


def normalized_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return the semantic result form used for replay and digest derivation."""

    return normalized_result_payload(value)


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "context_receipt_digest",
    "fact_digest",
    "harmonization_support_receipt_digest",
    "normalized_context_receipt",
    "normalized_dimension_assessment",
    "normalized_envelope",
    "normalized_envelope_assessment",
    "normalized_fact",
    "normalized_harmonization_support_receipt",
    "normalized_policy",
    "normalized_prerequisites",
    "normalized_profile",
    "normalized_quality_support_receipt",
    "normalized_remediation",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "policy_digest",
    "prerequisites_digest",
    "profile_digest",
    "quality_support_receipt_digest",
    "result_payload_digest",
]
