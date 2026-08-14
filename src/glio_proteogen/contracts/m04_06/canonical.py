"""Semantic canonicalization for M04-06 proteoform harmonization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from glio_proteogen.contracts.m04_05 import normalized_result as normalized_m0405_result
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest

_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    from glio_proteogen.kernel.strict_json import strict_json_loads  # noqa: PLC0415

    decoded = strict_json_loads(canonical_json_bytes(value))
    if not isinstance(decoded, dict):  # pragma: no cover - contract roots are objects.
        raise TypeError("M04-06 canonical object root must be a mapping")
    return decoded


def _sort(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_target_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["posterior_digests"] = tuple(sorted(data["posterior_digests"]))
    data["contamination_flag_ids"] = tuple(sorted(data["contamination_flag_ids"]))
    return data


def target_binding_digest(
    values: list[BaseModel | dict[str, Any]] | tuple[BaseModel | dict[str, Any], ...],
) -> Sha256Digest:
    return sha256_digest(_sort(tuple(normalized_target_receipt(item) for item in values)))


def normalized_artifact_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["targets"] = _sort(tuple(normalized_target_receipt(item) for item in data["targets"]))
    return data


def normalized_artifact_receipt_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_artifact_receipt(value)
    data.pop("receipt_digest", None)
    return data


def artifact_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_artifact_receipt_payload(value))


def normalized_factor_level(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_observation(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["artifact_posterior_digests"] = tuple(sorted(data["artifact_posterior_digests"]))
    data["artifact_contamination_flag_ids"] = tuple(sorted(data["artifact_contamination_flag_ids"]))
    data["factor_levels"] = _sort(
        tuple(normalized_factor_level(item) for item in data["factor_levels"])
    )
    data["evidence"] = _sort(data["evidence"])
    return data


def observation_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_observation(value))


def normalized_invariant(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["left_target_ids"] = tuple(sorted(data["left_target_ids"]))
    data["right_target_ids"] = tuple(sorted(data["right_target_ids"]))
    return data


def invariant_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_invariant(value))


def normalized_support_ledger(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["observations"] = _sort(
        tuple(normalized_observation(item) for item in data["observations"])
    )
    data["invariants"] = _sort(tuple(normalized_invariant(item) for item in data["invariants"]))
    return data


def normalized_support_ledger_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_support_ledger(value)
    data.pop("ledger_digest", None)
    return data


def support_ledger_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_support_ledger_payload(value))


def normalized_stage(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["estimation_anchor_ids"] = tuple(sorted(data["estimation_anchor_ids"]))
    data["validation_anchor_ids"] = tuple(sorted(data["validation_anchor_ids"]))
    return data


def stage_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_stage(value))


def normalized_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in (
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
    ):
        data[field] = tuple(sorted(data[field]))
    data["stages"] = tuple(
        sorted(
            (normalized_stage(item) for item in data["stages"]),
            key=lambda item: item["ordinal"],
        )
    )
    return data


def profile_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_profile(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["profiles"] = _sort(tuple(normalized_profile(item) for item in data["profiles"]))
    return data


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"proteoform_harmonization_policy": normalized_policy(value)})


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["artifact_result"] = normalized_m0405_result(data["artifact_result"])
    data["artifact_receipt"] = normalized_artifact_receipt(data["artifact_receipt"])
    if data["support_ledger"] is not None:
        data["support_ledger"] = normalized_support_ledger(data["support_ledger"])
    data["policy"] = normalized_policy(data["policy"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_level_shift(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_adjustment(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_stage_transformation(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["level_shifts"] = _sort(
        tuple(normalized_level_shift(item) for item in data["level_shifts"])
    )
    data["clipped_target_ids"] = tuple(sorted(data["clipped_target_ids"]))
    return data


def normalized_transformation_manifest(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["stages"] = tuple(
        sorted(
            (normalized_stage_transformation(item) for item in data["stages"]),
            key=lambda item: item["ordinal"],
        )
    )
    return data


def normalized_transformation_manifest_payload(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    data = normalized_transformation_manifest(value)
    data.pop("manifest_digest", None)
    return data


def transformation_manifest_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_transformation_manifest_payload(value))


def normalized_harmonized_value(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["adjustments"] = tuple(
        sorted(
            (normalized_adjustment(item) for item in data["adjustments"]),
            key=lambda item: item["ordinal"],
        )
    )
    return data


def normalized_analysis(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["values"] = _sort(tuple(normalized_harmonized_value(item) for item in data["values"]))
    return data


def normalized_analysis_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_analysis(value)
    data.pop("analysis_digest", None)
    return data


def analysis_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_analysis_payload(value))


def normalized_finding(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in ("stage_ids", "target_ids", "invariant_ids"):
        data[field] = tuple(sorted(data[field]))
    return data


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["result_digest"] = _DIGEST_SENTINEL
    data["request"] = normalized_request(data["request"])
    if data["analysis"] is not None:
        data["analysis"] = normalized_analysis(data["analysis"])
    if data["transformation_manifest"] is not None:
        data["transformation_manifest"] = normalized_transformation_manifest(
            data["transformation_manifest"]
        )
    for field in ("technical_effect_diagnostics", "invariant_diagnostics"):
        data[field] = _sort(data[field])
    data["findings"] = _sort(tuple(normalized_finding(item) for item in data["findings"]))
    data["provenance"]["input_digests"] = tuple(sorted(data["provenance"]["input_digests"]))
    data["provenance"]["control_decisions"] = _sort(data["provenance"]["control_decisions"])
    data["evidence"] = _sort(data["evidence"])
    data["limitations"] = _sort(data["limitations"])
    data["uncertainty"]["sensitivity_notes"] = tuple(
        sorted(data["uncertainty"]["sensitivity_notes"])
    )
    return data


def normalized_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return normalized_result_payload(value)


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "analysis_digest",
    "artifact_receipt_digest",
    "canonical_request_digest",
    "configuration_digest",
    "invariant_digest",
    "normalized_adjustment",
    "normalized_analysis",
    "normalized_analysis_payload",
    "normalized_artifact_receipt",
    "normalized_artifact_receipt_payload",
    "normalized_factor_level",
    "normalized_finding",
    "normalized_harmonized_value",
    "normalized_invariant",
    "normalized_level_shift",
    "normalized_observation",
    "normalized_policy",
    "normalized_profile",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "normalized_stage",
    "normalized_stage_transformation",
    "normalized_support_ledger",
    "normalized_support_ledger_payload",
    "normalized_target_receipt",
    "normalized_transformation_manifest",
    "normalized_transformation_manifest_payload",
    "observation_digest",
    "policy_digest",
    "profile_digest",
    "result_payload_digest",
    "stage_digest",
    "support_ledger_digest",
    "target_binding_digest",
    "transformation_manifest_digest",
]
