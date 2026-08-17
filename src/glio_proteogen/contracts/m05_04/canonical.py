"""Semantic canonicalization for M05-04 ptm_localization quality computation."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Final, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m05_03 import (
    normalized_result as normalized_m0503_result,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest

_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


def _python(value: Any) -> Any:  # noqa: ANN401 - recursive canonical JSON shape.
    value_mro = type.__getattribute__(type(value), "__mro__")
    if BaseModel in value_mro:
        dumped = BaseModel.model_dump(value, mode="python", exclude_none=False)
        return _python(dumped)
    if dict in value_mro:
        mapping = cast("dict[object, object]", value)
        keys = dict.keys(mapping)
        if any(type(key) is not str for key in keys):
            raise TypeError("canonical M05-04 object keys must be exact strings")
        return {key: _python(dict.__getitem__(mapping, key)) for key in dict.keys(mapping)}
    if list in value_mro:
        list_values = cast("list[object]", value)
        return tuple(_python(item) for item in list.__iter__(list_values))
    if tuple in value_mro:
        tuple_values = cast("tuple[object, ...]", value)
        return tuple(_python(item) for item in tuple.__iter__(tuple_values))
    return value


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return dict(_python(value))


def _sorted(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_threshold(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def threshold_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_threshold(value))


def normalized_assay_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in (
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_unit_system_versions",
    ):
        data[field] = tuple(sorted(data[field]))
    data["thresholds"] = _sorted(data["thresholds"])
    return data


def profile_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_assay_profile(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["profiles"] = _sorted(tuple(normalized_assay_profile(item) for item in data["profiles"]))
    return data


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"ptm_localization_quality_policy": normalized_policy(value)})


def normalized_role_facts(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def role_facts_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_role_facts(value))


def normalized_fact_ledger(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["role_facts"] = _sorted(data["role_facts"])
    return data


def normalized_fact_ledger_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_fact_ledger(value)
    data["ledger_digest"] = _ZERO_DIGEST
    return data


def fact_ledger_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_fact_ledger_payload(value))


def normalized_raw_input_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return normalized_m0503_result(_dump(value))


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["raw_input_result"] = normalized_raw_input_result(data["raw_input_result"])
    data["policy"] = normalized_policy(data["policy"])
    if data["fact_ledger"] is not None:
        data["fact_ledger"] = normalized_fact_ledger(data["fact_ledger"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def context_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    data = _dump(value)
    return sha256_digest(data.get("context", data))


def normalized_metric(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def metric_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_metric(value))


def normalized_finding(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["roles"] = tuple(sorted(data["roles"]))
    data["metric_codes"] = tuple(sorted(data["metric_codes"]))
    return data


def normalized_assay_quality(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["metrics"] = _sorted(data["metrics"])
    data["finding_codes"] = tuple(sorted(data["finding_codes"]))
    return data


def assay_quality_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_assay_quality(value))


def normalized_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["receipt_digest"] = _ZERO_DIGEST
    data["selected_profile_digests"] = tuple(sorted(data["selected_profile_digests"]))
    data["assay_quality_digests"] = tuple(sorted(data["assay_quality_digests"]))
    data["finding_codes"] = tuple(sorted(data["finding_codes"]))
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
    data["assay_quality"] = _sorted(
        tuple(normalized_assay_quality(item) for item in data["assay_quality"])
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
    "assay_quality_digest",
    "canonical_request_digest",
    "configuration_digest",
    "context_digest",
    "fact_ledger_digest",
    "metric_digest",
    "normalized_assay_profile",
    "normalized_assay_quality",
    "normalized_fact_ledger",
    "normalized_finding",
    "normalized_metric",
    "normalized_policy",
    "normalized_raw_input_result",
    "normalized_receipt",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "normalized_role_facts",
    "normalized_threshold",
    "policy_digest",
    "profile_digest",
    "receipt_digest",
    "result_payload_digest",
    "role_facts_digest",
    "threshold_digest",
]
