"""Canonical normalization and digest functions for M03-01."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python", exclude_none=False)
    return deepcopy(value)


def _sorted(items: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(items, key=canonical_json_bytes))


def normalized_protocol(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Normalize only fields whose ordering has no protocol meaning."""

    data = _dump(value)
    data["error_control"]["thresholds"] = _sorted(data["error_control"]["thresholds"])
    data["complex_activity_handoff"]["required_receipt_roles"] = tuple(
        sorted(data["complex_activity_handoff"]["required_receipt_roles"])
    )
    data["required_identity_keys"] = tuple(sorted(data["required_identity_keys"]))
    data["declared_unresolved_states"] = tuple(sorted(data["declared_unresolved_states"]))
    return data


def normalized_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["approved_applicabilities"] = _sorted(data["approved_applicabilities"])
    data["approved_search_spaces"] = _sorted(data["approved_search_spaces"])
    data["approved_controlled_vocabularies"] = _sorted(
        data["approved_controlled_vocabularies"]
    )
    for field in (
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_unit_system_versions",
        "allowed_target_decoy_strategies",
        "allowed_protein_error_measures",
        "allowed_shared_peptide_strategies",
        "allowed_representative_selections",
    ):
        data[field] = tuple(sorted(data[field]))
    return data


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["protocol_schema"] = normalized_protocol(data["protocol_schema"])
    data["conformance_profile"] = normalized_profile(data["conformance_profile"])
    return data


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["result_digest"] = "sha256:" + ("0" * 64)
    data["protocol_schema"] = normalized_protocol(data["protocol_schema"])
    data["conformance_profile"] = normalized_profile(data["conformance_profile"])
    data["findings"] = _sorted(data["findings"])
    data["provenance"]["input_digests"] = tuple(
        sorted(data["provenance"]["input_digests"])
    )
    data["provenance"]["control_decisions"] = _sorted(
        data["provenance"]["control_decisions"]
    )
    data["evidence"] = _sorted(data["evidence"])
    data["limitations"] = _sorted(data["limitations"])
    data["uncertainty"]["sensitivity_notes"] = tuple(
        sorted(data["uncertainty"]["sensitivity_notes"])
    )
    return data


def protocol_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_protocol(value))


def profile_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_profile(value))


def configuration_digest(
    protocol: BaseModel | dict[str, Any],
    profile: BaseModel | dict[str, Any],
) -> Sha256Digest:
    return sha256_digest(
        {
            "protocol_digest": protocol_digest(protocol),
            "profile_digest": profile_digest(profile),
        }
    )


def protocol_section_digest(
    value: BaseModel | dict[str, Any],
    section: str,
) -> Sha256Digest:
    """Digest one protocol section using the same semantic normalization as the protocol."""

    return sha256_digest(normalized_protocol(value)[section])


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "normalized_profile",
    "normalized_protocol",
    "normalized_request",
    "normalized_result_payload",
    "profile_digest",
    "protocol_digest",
    "protocol_section_digest",
    "result_payload_digest",
]
