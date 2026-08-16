"""Adversarial closure and shape tests for M15-04."""

# ruff: noqa: E501, PT011

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m15_04 import (
    ComplexActivityMechanismInferenceResult,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismInferenceStatus,
    result_payload_digest,
)
from glio_proteogen.kernel.models import EvidenceReference, SupportStatus
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_04_network_state_mechanism_inference import (
    M1504MechanismInference,
)
from tests.modules.c15_longitudinal_recurrence.test_m15_04_engine import _artifact, _request


def _inferred() -> ComplexActivityMechanismInferenceResult:
    return M1504MechanismInference().infer(_request())


def _closed_error(result: ComplexActivityMechanismInferenceResult, **updates: Any) -> ValueError:
    candidate = result.model_copy(update=updates)
    with pytest.raises(ValueError) as caught:
        candidate.result_is_closed()
    return caught.value


def _counter_evidence() -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact("counter"),
            role="counter_evidence",
            claim="Counter-evidence remains visible.",
        ),
    )


def test_estimate_shape_rejects_unordered_or_mixed_posterior_state() -> None:
    with pytest.raises(ValueError, match="ordered bounds"):
        MechanismEstimate(
            estimate_id="estimate.invalid",
            mechanism_id="mechanism.invalid",
            label="Invalid posterior",
            kind=MechanismEstimateKind.POSTERIOR,
            posterior_probability=0.9,
            lower_bound=0.8,
            upper_bound=0.7,
            assumptions=("Assumption.",),
            alternatives=("Alternative.",),
            counter_evidence=_counter_evidence(),
        )
    with pytest.raises(ValueError, match="state estimate"):
        MechanismEstimate(
            estimate_id="estimate.invalid-state",
            mechanism_id="mechanism.invalid",
            label="Invalid state",
            kind=MechanismEstimateKind.STATE,
            state_value="state",
            lower_bound=0.1,
            assumptions=("Assumption.",),
            alternatives=("Alternative.",),
            counter_evidence=_counter_evidence(),
        )


def test_result_closure_rejects_duplicate_ids_digest_and_unsafe_states() -> None:
    result = _inferred()
    assert "derived from request digest" in str(_closed_error(result, result_id="result.invalid"))
    assert "estimate ids" in str(
        _closed_error(result, estimates=(result.estimates[0], result.estimates[0]))
    )
    assert "evidence references" in str(
        _closed_error(
            result,
            evidence=(result.evidence[0].model_copy(update={"role": "counter_evidence"}),),
        )
    )
    assert "supported mechanism estimates" in str(_closed_error(result, human_review_required=True))


def test_abstention_closure_requires_review_and_safe_support() -> None:
    result = _inferred()
    candidate = result.model_copy(
        update={
            "status": MechanismInferenceStatus.ABSTAINED,
            "estimates": (),
            "abstention_reason": None,
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.REVIEW_REQUIRED}
            ),
            "human_review_required": True,
        }
    )
    with pytest.raises(ValueError, match="abstained result"):
        candidate.result_is_closed()
    candidate = candidate.model_copy(update={"abstention_reason": "Review required."})
    candidate = candidate.model_copy(update={"result_digest": result_payload_digest(candidate)})
    assert candidate.result_is_closed() is candidate


def test_invalid_request_shape_is_rejected_without_coercion() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["hypothesis_registry_result"] = request.hypothesis_registry_result.model_copy(
        update={"media_type": "application/json"}
    )
    with pytest.raises(ValidationError, match="provisional M15-01"):
        type(request).model_validate(payload)
