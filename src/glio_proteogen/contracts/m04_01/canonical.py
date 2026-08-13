"""Canonical normalization and digest helpers for M04-01."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_SECTION_ORDER = {
    section: index
    for index, section in enumerate(
        (
            "applicability",
            "identity",
            "metadata_versions",
            "reference_bundle",
            "coordinate_mapping",
            "evidence_eligibility",
            "isoform_discrimination",
            "modification_localization",
            "quantification",
            "unresolved_semantics",
            "discordance_handoff",
        )
    )
}


def _python(value: Any) -> Any:  # noqa: ANN401 - recursive JSON-compatible shape.
    if isinstance(value, BaseModel):
        return _python(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, dict):
        return {key: _python(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_python(item) for item in value)
    return deepcopy(value)


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return dict(_python(value))


def _sorted(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def _section_sorted(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=lambda item: _SECTION_ORDER[str(item["section"])]))


def normalized_reference_bundle(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def reference_bundle_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_reference_bundle(value))


def normalized_coordinate_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def coordinate_policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_coordinate_policy(value))


def normalized_protocol(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["required_identity_keys"] = _sorted(data["required_identity_keys"])
    data["declared_unresolved_states"] = _sorted(data["declared_unresolved_states"])
    data["evidence_eligibility"]["eligible_evidence_classes"] = _sorted(
        data["evidence_eligibility"]["eligible_evidence_classes"]
    )
    data["isoform_discrimination"]["accepted_discriminators"] = _sorted(
        data["isoform_discrimination"]["accepted_discriminators"]
    )
    data["modification_localization"]["declared_states"] = _sorted(
        data["modification_localization"]["declared_states"]
    )
    data["discordance_handoff"]["required_receipt_roles"] = _sorted(
        data["discordance_handoff"]["required_receipt_roles"]
    )
    return data


def protocol_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_protocol(value))


def protocol_section_digest(
    value: BaseModel | dict[str, Any],
    section: str,
) -> Sha256Digest:
    data = normalized_protocol(value)
    sections: dict[str, object] = {
        "applicability": data["applicability"],
        "identity": data["required_identity_keys"],
        "metadata_versions": {
            key: data[key]
            for key in (
                "assay_protocol_version",
                "specimen_processing_version",
                "controlled_vocabulary_id",
                "controlled_vocabulary_version",
                "unit_system_version",
            )
        },
        "reference_bundle": data["reference_bundle"],
        "coordinate_mapping": data["coordinate_policy"],
        "evidence_eligibility": data["evidence_eligibility"],
        "isoform_discrimination": data["isoform_discrimination"],
        "modification_localization": data["modification_localization"],
        "quantification": data["quantification"],
        "unresolved_semantics": data["declared_unresolved_states"],
        "discordance_handoff": data["discordance_handoff"],
    }
    return sha256_digest(sections[section])


def normalized_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in (
        "approved_applicabilities",
        "approved_reference_bundles",
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabularies",
        "approved_unit_system_versions",
        "approved_coordinate_profiles",
        "approved_quantification_pairs",
        "approved_evidence_classes",
        "approved_labile_modification_handlings",
        "approved_isoform_discriminators",
    ):
        data[field] = _sorted(data[field])
    return data


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


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["protocol_schema"] = normalized_protocol(data["protocol_schema"])
    data["conformance_profile"] = normalized_profile(data["conformance_profile"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["receipt_digest"] = _ZERO_DIGEST
    data["sections"] = _section_sorted(data["sections"])
    return data


def receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_receipt(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    defaults: dict[str, object] = {
        "output_type": "proteoform_protocol_conformance_result",
        "result_version": "1.0.0",
        "parent_target": "protein_rna_discordance",
        "emits_protein_rna_discordance": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_proteoform_or_isoform": False,
        "localizes_modification": False,
        "infers_kinase_activity": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream_evidence": False,
        "infers_identity_or_consent": False,
    }
    for field, default in defaults.items():
        data.setdefault(field, default)
    data["result_digest"] = _ZERO_DIGEST
    data["request"] = normalized_request(data["request"])
    data["receipt"] = _dump(data["receipt"])
    data["receipt"]["sections"] = _section_sorted(data["receipt"]["sections"])
    data["findings"] = _section_sorted(data["findings"])
    data["evidence"] = _sorted(data["evidence"])
    data["limitations"] = _sorted(data["limitations"])
    data["provenance"]["input_digests"] = _sorted(data["provenance"]["input_digests"])
    data["provenance"]["control_decisions"] = _sorted(data["provenance"]["control_decisions"])
    data["uncertainty"]["sensitivity_notes"] = _sorted(data["uncertainty"]["sensitivity_notes"])
    return data


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "coordinate_policy_digest",
    "normalized_coordinate_policy",
    "normalized_profile",
    "normalized_protocol",
    "normalized_receipt",
    "normalized_reference_bundle",
    "normalized_request",
    "normalized_result_payload",
    "profile_digest",
    "protocol_digest",
    "protocol_section_digest",
    "receipt_digest",
    "reference_bundle_digest",
    "result_payload_digest",
]
