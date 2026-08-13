"""Semantic canonicalization for M03-04 protein-inference quality."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest

_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return a canonical-JSON primitive shape with typed/dict parity."""

    from glio_proteogen.kernel.strict_json import strict_json_loads  # noqa: PLC0415

    decoded = strict_json_loads(canonical_json_bytes(value))
    if not isinstance(decoded, dict):  # pragma: no cover - contract roots are objects.
        raise TypeError("M03-04 canonical object root must be a mapping")
    return decoded


def _sort(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_threshold(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def threshold_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_threshold(value))


def normalized_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in (
        "approved_assay_protocol_versions",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
    ):
        data[field] = tuple(sorted(data[field]))
    data["thresholds"] = _sort(data["thresholds"])
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
    return sha256_digest({"protein_inference_quality_policy": normalized_policy(value)})


def normalized_source_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["diagnostic_codes"] = tuple(sorted(data["diagnostic_codes"]))
    return data


def normalized_claim_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["finding_codes"] = tuple(sorted(data["finding_codes"]))
    return data


def normalized_raw_quality_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["sources"] = _sort(
        tuple(normalized_source_receipt(item) for item in data["sources"])
    )
    data["claims"] = _sort(
        tuple(normalized_claim_receipt(item) for item in data["claims"])
    )
    return data


def normalized_raw_quality_receipt_payload(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    data = normalized_raw_quality_receipt(value)
    data.pop("receipt_digest", None)
    return data


def raw_quality_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_raw_quality_receipt_payload(value))


def source_binding_digest(
    values: list[BaseModel | dict[str, Any]] | tuple[BaseModel | dict[str, Any], ...],
) -> Sha256Digest:
    return sha256_digest(
        _sort(tuple(normalized_source_receipt(item) for item in values))
    )


def claim_binding_digest(
    values: list[BaseModel | dict[str, Any]] | tuple[BaseModel | dict[str, Any], ...],
) -> Sha256Digest:
    return sha256_digest(_sort(tuple(normalized_claim_receipt(item) for item in values)))


def normalized_fact_ledger(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_fact_ledger_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_fact_ledger(value)
    data.pop("ledger_digest", None)
    return data


def fact_ledger_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_fact_ledger_payload(value))


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["raw_quality_receipt"] = normalized_raw_quality_receipt(
        data["raw_quality_receipt"]
    )
    if data["fact_ledger"] is not None:
        data["fact_ledger"] = normalized_fact_ledger(data["fact_ledger"])
    data["policy"] = normalized_policy(data["policy"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_finding(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in ("metric_codes", "source_ids", "claim_ids"):
        data[field] = tuple(sorted(data[field]))
    return data


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["result_digest"] = _DIGEST_SENTINEL
    data["request"] = normalized_request(data["request"])
    data["metrics"] = _sort(data["metrics"])
    data["findings"] = _sort(
        tuple(normalized_finding(item) for item in data["findings"])
    )
    data["provenance"]["input_digests"] = tuple(
        sorted(data["provenance"]["input_digests"])
    )
    data["provenance"]["control_decisions"] = _sort(
        data["provenance"]["control_decisions"]
    )
    data["evidence"] = _sort(data["evidence"])
    data["limitations"] = _sort(data["limitations"])
    data["uncertainty"]["sensitivity_notes"] = tuple(
        sorted(data["uncertainty"]["sensitivity_notes"])
    )
    return data


def normalized_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Strict public result normalizer retained as an explicit stable helper."""

    return normalized_result_payload(value)


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "claim_binding_digest",
    "configuration_digest",
    "fact_ledger_digest",
    "normalized_claim_receipt",
    "normalized_fact_ledger",
    "normalized_fact_ledger_payload",
    "normalized_finding",
    "normalized_policy",
    "normalized_profile",
    "normalized_raw_quality_receipt",
    "normalized_raw_quality_receipt_payload",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "normalized_source_receipt",
    "normalized_threshold",
    "policy_digest",
    "profile_digest",
    "raw_quality_receipt_digest",
    "result_payload_digest",
    "source_binding_digest",
    "threshold_digest",
]
