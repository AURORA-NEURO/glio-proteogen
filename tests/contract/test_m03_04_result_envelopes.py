"""Adversarial replay checks for the complete M03-04 result envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from evals.m03_04.run import build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m03_04 import (
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceQualityResult,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    compute_protein_inference_quality,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(scope="module")
def canonical_payload() -> dict[str, Any]:
    result = compute_protein_inference_quality(build_scenario().request)
    return cast(
        "dict[str, Any]",
        strict_json_loads(canonical_json_bytes(result)),
    )


def _validate(payload: dict[str, Any]) -> ProteinInferenceQualityResult:
    return ProteinInferenceQualityResult.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _mutate_completion(payload: dict[str, Any]) -> None:
    payload["completed_at"] = "2026-08-13T00:00:01Z"


def _mutate_support(payload: dict[str, Any]) -> None:
    payload["support"]["rationale"] = "forged support rationale"


def _mutate_uncertainty(payload: dict[str, Any]) -> None:
    payload["uncertainty"]["measurement"]["rationale"] = "forged uncertainty rationale"


def _mutate_provenance(payload: dict[str, Any]) -> None:
    payload["provenance"]["activity_id"] = "activity.m0304.forged"


def _mutate_evidence(payload: dict[str, Any]) -> None:
    payload["evidence"][0]["claim"] = "forged evidence claim"


def _mutate_limitations(payload: dict[str, Any]) -> None:
    payload["limitations"][0]["statement"] = "forged limitation statement"


def _mutate_review(payload: dict[str, Any]) -> None:
    payload["human_review_required"] = True


@pytest.mark.parametrize(
    "mutate",
    [
        _mutate_completion,
        _mutate_support,
        _mutate_uncertainty,
        _mutate_provenance,
        _mutate_evidence,
        _mutate_limitations,
        _mutate_review,
    ],
    ids=(
        "completion",
        "support",
        "uncertainty",
        "provenance",
        "evidence",
        "limitations",
        "human-review",
    ),
)
def test_resigned_semantic_envelope_forgery_is_rejected(
    canonical_payload: dict[str, Any],
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    payload = cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(canonical_payload)))
    mutate(payload)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        _validate(payload)


def test_stale_result_digest_is_rejected(canonical_payload: dict[str, Any]) -> None:
    payload = cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(canonical_payload)))
    payload["completed_at"] = "2026-08-13T00:00:01Z"
    with pytest.raises(ValidationError):
        _validate(payload)


def test_duplicate_metric_code_is_rejected(canonical_payload: dict[str, Any]) -> None:
    payload = cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(canonical_payload)))
    payload["metrics"][0] = payload["metrics"][1]
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        _validate(payload)


def test_incomplete_traversed_metric_set_is_rejected(
    canonical_payload: dict[str, Any],
) -> None:
    payload = cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(canonical_payload)))
    payload["metrics"].pop()
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        _validate(payload)


@pytest.mark.parametrize(
    ("reference", "state"),
    [
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("identity_lineage", "unresolved"),
    ],
)
def test_typed_request_rejects_each_authorization_class(
    canonical_payload: dict[str, Any],
    reference: str,
    state: str,
) -> None:
    request = cast(
        "dict[str, Any]",
        strict_json_loads(canonical_json_bytes(canonical_payload["request"])),
    )
    request["context"]["references"][reference]["state"] = state
    with pytest.raises(ValidationError):
        ComputeProteinInferenceQualityRequest.model_validate_json(
            canonical_json_bytes(request),
            strict=True,
        )
