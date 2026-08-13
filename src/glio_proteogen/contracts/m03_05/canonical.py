"""Semantic canonicalization for M03-05 artifact and contamination contracts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final, cast

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest

_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    # This is trusted internal canonical materialization. A valid bounded output
    # can exceed the public 4 MiB request ceiling, so the ingress parser must not
    # be reused here.
    decoded = json.loads(canonical_json_bytes(value))
    if not isinstance(decoded, dict):  # pragma: no cover - contract roots are objects.
        raise TypeError("M03-05 canonical object root must be a mapping")
    return cast("dict[str, Any]", decoded)


def _sort(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_threshold(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["applicable_unit_kinds"] = tuple(sorted(data["applicable_unit_kinds"]))
    return data


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
    data["thresholds"] = _sort(tuple(normalized_threshold(item) for item in data["thresholds"]))
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
    return sha256_digest({"protein_inference_artifact_policy": normalized_policy(value)})


def normalized_source_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["diagnostic_codes"] = tuple(sorted(data["diagnostic_codes"]))
    return data


def normalized_claim_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["finding_codes"] = tuple(sorted(data["finding_codes"]))
    return data


def normalized_quality_metric_receipt(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    return _dump(value)


def source_binding_digest(
    values: list[BaseModel | dict[str, Any]] | tuple[BaseModel | dict[str, Any], ...],
) -> Sha256Digest:
    return sha256_digest(_sort(tuple(normalized_source_receipt(item) for item in values)))


def claim_binding_digest(
    values: list[BaseModel | dict[str, Any]] | tuple[BaseModel | dict[str, Any], ...],
) -> Sha256Digest:
    return sha256_digest(_sort(tuple(normalized_claim_receipt(item) for item in values)))


def quality_metric_binding_digest(
    values: list[BaseModel | dict[str, Any]] | tuple[BaseModel | dict[str, Any], ...],
) -> Sha256Digest:
    return sha256_digest(_sort(tuple(normalized_quality_metric_receipt(item) for item in values)))


def normalized_artifact_quality_receipt(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    data = _dump(value)
    data["sources"] = _sort(tuple(normalized_source_receipt(item) for item in data["sources"]))
    data["claims"] = _sort(tuple(normalized_claim_receipt(item) for item in data["claims"]))
    data["quality_metrics"] = _sort(
        tuple(normalized_quality_metric_receipt(item) for item in data["quality_metrics"])
    )
    return data


def normalized_artifact_quality_receipt_payload(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    data = normalized_artifact_quality_receipt(value)
    data.pop("receipt_digest", None)
    return data


def artifact_quality_receipt_digest(
    value: BaseModel | dict[str, Any],
) -> Sha256Digest:
    return sha256_digest(normalized_artifact_quality_receipt_payload(value))


def normalized_signal(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_evidence_unit(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["source_ids"] = tuple(sorted(data["source_ids"]))
    data["claim_ids"] = tuple(sorted(data["claim_ids"]))
    data["signals"] = _sort(tuple(normalized_signal(item) for item in data["signals"]))
    return data


def normalized_artifact_evidence_ledger(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    data = _dump(value)
    data["units"] = _sort(tuple(normalized_evidence_unit(item) for item in data["units"]))
    return data


def normalized_artifact_evidence_ledger_payload(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    data = normalized_artifact_evidence_ledger(value)
    data.pop("ledger_digest", None)
    return data


def artifact_evidence_ledger_digest(
    value: BaseModel | dict[str, Any],
) -> Sha256Digest:
    return sha256_digest(normalized_artifact_evidence_ledger_payload(value))


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["quality_receipt"] = normalized_artifact_quality_receipt(data["quality_receipt"])
    if data["evidence_ledger"] is not None:
        data["evidence_ledger"] = normalized_artifact_evidence_ledger(data["evidence_ledger"])
    data["policy"] = normalized_policy(data["policy"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_finding(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["signal_codes"] = tuple(sorted(data["signal_codes"]))
    data["unit_ids"] = tuple(sorted(data["unit_ids"]))
    return data


def normalized_exclusion_mask(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    for field in ("retain_unit_ids", "review_unit_ids", "exclude_unit_ids"):
        data[field] = tuple(sorted(data[field]))
    return data


def normalized_posterior(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["contributing_signal_codes"] = tuple(sorted(data["contributing_signal_codes"]))
    return data


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["result_digest"] = _DIGEST_SENTINEL
    data["request"] = normalized_request(data["request"])
    for field in ("signal_scores", "contamination_flags"):
        data[field] = _sort(data[field])
    data["artifact_posteriors"] = _sort(
        tuple(normalized_posterior(item) for item in data["artifact_posteriors"])
    )
    data["exclusion_mask"] = normalized_exclusion_mask(data["exclusion_mask"])
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
    "artifact_evidence_ledger_digest",
    "artifact_quality_receipt_digest",
    "canonical_request_digest",
    "claim_binding_digest",
    "configuration_digest",
    "normalized_artifact_evidence_ledger",
    "normalized_artifact_evidence_ledger_payload",
    "normalized_artifact_quality_receipt",
    "normalized_artifact_quality_receipt_payload",
    "normalized_claim_receipt",
    "normalized_evidence_unit",
    "normalized_exclusion_mask",
    "normalized_finding",
    "normalized_policy",
    "normalized_posterior",
    "normalized_profile",
    "normalized_quality_metric_receipt",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "normalized_signal",
    "normalized_source_receipt",
    "normalized_threshold",
    "policy_digest",
    "profile_digest",
    "quality_metric_binding_digest",
    "result_payload_digest",
    "source_binding_digest",
    "threshold_digest",
]
