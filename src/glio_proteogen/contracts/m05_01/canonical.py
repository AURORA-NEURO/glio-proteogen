"""Semantic canonicalization for M05-01 protocol conformance."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest

_ZERO_DIGEST = "sha256:" + ("0" * 64)


def _python(value: Any) -> Any:  # noqa: ANN401 - recursive canonical JSON shape.
    value_mro = type.__getattribute__(type(value), "__mro__")
    if BaseModel in value_mro:
        return _python(BaseModel.model_dump(value, mode="python", exclude_none=False))
    if dict in value_mro:
        mapping = cast("dict[object, object]", value)
        if any(type(key) is not str for key in dict.keys(mapping)):
            raise TypeError("canonical M05-01 object keys must be exact strings")
        return {key: _python(dict.__getitem__(mapping, key)) for key in dict.keys(mapping)}
    if list in value_mro:
        return tuple(_python(item) for item in list.__iter__(cast("list[object]", value)))
    if tuple in value_mro:
        return tuple(_python(item) for item in tuple.__iter__(cast("tuple[object, ...]", value)))
    return value


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return dict(_python(value))


def _sorted(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_reference_bundle(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["references"] = _sorted(data["references"])
    return data


def reference_bundle_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_reference_bundle(value))


def assay_specimen_policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_dump(value))


def normalized_protocol(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["required_identity_keys"] = tuple(sorted(data["required_identity_keys"]))
    data["declared_unresolved_states"] = tuple(sorted(data["declared_unresolved_states"]))
    data["controlled_vocabularies"] = _sorted(data["controlled_vocabularies"])
    data["unit_policies"] = _sorted(data["unit_policies"])
    data["metadata_fields"] = _sorted(data["metadata_fields"])
    data["compatibility_rules"] = _sorted(data["compatibility_rules"])
    data["reference_bundle"] = normalized_reference_bundle(data["reference_bundle"])
    return data


def protocol_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_protocol(value))


def normalized_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in (
        "approved_reference_bundles",
        "approved_protocol_versions",
        "approved_assay_versions",
        "approved_specimen_versions",
        "approved_vocabulary_versions",
        "approved_unit_system_versions",
    ):
        data[field] = _sorted(data[field])
    return data


def profile_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_profile(value))


def configuration_digest(
    protocol: BaseModel | dict[str, Any], profile: BaseModel | dict[str, Any]
) -> Sha256Digest:
    return sha256_digest(
        {
            "ptm_localization_protocol": normalized_protocol(protocol),
            "reviewed_conformance_profile": normalized_profile(profile),
        }
    )


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["protocol_schema"] = normalized_protocol(data["protocol_schema"])
    data["conformance_profile"] = normalized_profile(data["conformance_profile"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_finding(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["receipt_digest"] = _ZERO_DIGEST
    data["sections"] = _sorted(data["sections"])
    return data


def receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_receipt(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    source = _dump(value)
    data = deepcopy(source)
    data["result_digest"] = _ZERO_DIGEST
    data["request"] = normalized_request(data["request"])
    data["receipt"] = normalized_receipt(data["receipt"])
    data["receipt"]["receipt_digest"] = source["receipt"]["receipt_digest"]
    data["findings"] = _sorted(tuple(normalized_finding(item) for item in data["findings"]))
    data["evidence"] = _sorted(data["evidence"])
    data["limitations"] = _sorted(data["limitations"])
    data["provenance"]["input_digests"] = tuple(sorted(data["provenance"]["input_digests"]))
    data["provenance"]["control_decisions"] = _sorted(data["provenance"]["control_decisions"])
    data["uncertainty"]["sensitivity_notes"] = tuple(
        sorted(data["uncertainty"]["sensitivity_notes"])
    )
    return data


def normalized_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_result_payload(value)
    data["result_digest"] = _dump(value)["result_digest"]
    return data


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "assay_specimen_policy_digest",
    "canonical_request_digest",
    "configuration_digest",
    "normalized_finding",
    "normalized_profile",
    "normalized_protocol",
    "normalized_receipt",
    "normalized_reference_bundle",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "profile_digest",
    "protocol_digest",
    "receipt_digest",
    "reference_bundle_digest",
    "result_payload_digest",
]
