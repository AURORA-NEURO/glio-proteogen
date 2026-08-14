"""Semantic canonicalization for M04-05 artifact-contamination detection."""

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
            raise TypeError("canonical M04-05 object keys must be exact strings")
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


def normalized_threshold(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def threshold_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_threshold(value))


def normalized_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["approved_quality_contract_versions"] = tuple(
        sorted(data["approved_quality_contract_versions"])
    )
    data["thresholds"] = _sorted(data["thresholds"])
    return data


def profile_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_profile(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["profiles"] = _sorted(tuple(normalized_profile(item) for item in data["profiles"]))
    return data


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"artifact_contamination_policy": normalized_policy(value)})


def normalized_event(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["evidence"] = _sorted(data["evidence"])
    return data


def event_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_event(value))


def normalized_evidence_ledger(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["events"] = tuple(sorted(data["events"], key=lambda item: item["sequence"]))
    return data


def normalized_evidence_ledger_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_evidence_ledger(value)
    data["ledger_digest"] = _ZERO_DIGEST
    return data


def evidence_ledger_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_evidence_ledger_payload(value))


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["policy"] = normalized_policy(data["policy"])
    if data["evidence_ledger"] is not None:
        data["evidence_ledger"] = normalized_evidence_ledger(data["evidence_ledger"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_posterior(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["evidence"] = _sorted(data["evidence"])
    return data


def normalized_posterior_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_posterior(value)
    data["posterior_digest"] = _ZERO_DIGEST
    return data


def posterior_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_posterior_payload(value))


def normalized_contamination_flag(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["evidence"] = _sorted(data["evidence"])
    return data


def contamination_flag_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_contamination_flag(value))


def normalized_exclusion_mask_entry(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["triggering_posterior_digests"] = tuple(sorted(data["triggering_posterior_digests"]))
    data["triggering_flag_ids"] = tuple(sorted(data["triggering_flag_ids"]))
    data["evidence"] = _sorted(data["evidence"])
    return data


def normalized_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["receipt_digest"] = _ZERO_DIGEST
    for field in (
        "event_digests",
        "posterior_digests",
        "contamination_flag_digests",
        "excluded_target_ids",
        "finding_codes",
    ):
        data[field] = tuple(sorted(data[field]))
    return data


def receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_receipt(value))


def normalized_finding(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["target_ids"] = tuple(sorted(data["target_ids"]))
    data["detector_classes"] = tuple(sorted(data["detector_classes"]))
    return data


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    source = _dump(value)
    data = deepcopy(source)
    data["result_digest"] = _ZERO_DIGEST
    data["request"] = normalized_request(data["request"])
    data["receipt"] = normalized_receipt(data["receipt"])
    data["receipt"]["receipt_digest"] = source["receipt"]["receipt_digest"]
    data["artifact_posteriors"] = _sorted(
        tuple(normalized_posterior(item) for item in data["artifact_posteriors"])
    )
    data["contamination_flags"] = _sorted(
        tuple(normalized_contamination_flag(item) for item in data["contamination_flags"])
    )
    data["exclusion_mask"] = _sorted(
        tuple(normalized_exclusion_mask_entry(item) for item in data["exclusion_mask"])
    )
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
    "canonical_request_digest",
    "configuration_digest",
    "contamination_flag_digest",
    "event_digest",
    "evidence_ledger_digest",
    "normalized_contamination_flag",
    "normalized_event",
    "normalized_evidence_ledger",
    "normalized_evidence_ledger_payload",
    "normalized_exclusion_mask_entry",
    "normalized_finding",
    "normalized_policy",
    "normalized_posterior",
    "normalized_posterior_payload",
    "normalized_profile",
    "normalized_receipt",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "normalized_threshold",
    "policy_digest",
    "posterior_digest",
    "profile_digest",
    "receipt_digest",
    "result_payload_digest",
    "threshold_digest",
]
