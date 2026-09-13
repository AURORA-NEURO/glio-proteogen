"""Canonical projections for the provisional M12-06 contract spine."""

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


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    # Scenario ordering is transport noise; IDs define the semantic order for
    # typed replay and make equivalent JSON requests share one digest.
    scenarios = document.get("scenarios")
    if isinstance(scenarios, list):
        normalized_scenarios: list[Any] = []
        for item in scenarios:
            if isinstance(item, dict):
                normalized = dict(item)
                for field in ("baseline_measurements", "perturbed_measurements"):
                    measurements = normalized.get(field)
                    if isinstance(measurements, list):
                        normalized[field] = sorted(measurements)
                normalized_scenarios.append(normalized)
            else:
                normalized_scenarios.append(item)
        document["scenarios"] = sorted(
            normalized_scenarios,
            key=lambda item: (
                str(item.get("scenario_id", "")) if isinstance(item, dict) else str(item)
            ),
        )
    return document


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    document = _dump(value)
    document.pop("result_digest", None)
    return document


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
]
