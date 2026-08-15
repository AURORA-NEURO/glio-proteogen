"""Canonical JSON projections and digests for M05-05."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


def _without(value: BaseModel | dict[str, Any], *fields: str) -> dict[str, Any]:
    document = _dump(value)
    for field in fields:
        document.pop(field, None)
    return document


def normalized_threshold(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def threshold_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_threshold(value))


def normalized_profile(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def profile_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_profile(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"policy": normalized_policy(value)})


def normalized_event(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def event_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_event(value))


def normalized_evidence_ledger(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def evidence_ledger_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_without(value, "ledger_digest"))


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_posterior(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def posterior_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_without(value, "posterior_digest"))


def normalized_contamination_flag(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def contamination_flag_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_contamination_flag(value))


def normalized_exclusion_mask_entry(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_finding(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def normalized_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_without(value, "receipt_digest"))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _without(value, "result_digest")


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


def normalized_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "contamination_flag_digest",
    "event_digest",
    "evidence_ledger_digest",
    "normalized_contamination_flag",
    "normalized_event",
    "normalized_evidence_ledger",
    "normalized_exclusion_mask_entry",
    "normalized_finding",
    "normalized_policy",
    "normalized_posterior",
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
