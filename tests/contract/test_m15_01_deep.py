"""Adversarial closure and provenance tests for M15-01."""

# ruff: noqa: PLR2004, PT011

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m15_01 import (
    ComplexActivityHypothesisRegistryResult,
    FalsificationOutcome,
    HypothesisFinding,
    HypothesisFindingCode,
    HypothesisStatus,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_01_biological_hypothesis_registry import (  # noqa: E501
    M1501HypothesisRegistry,
)
from tests.modules.c15_longitudinal_recurrence.test_m15_01_engine import _request


def _supported() -> ComplexActivityHypothesisRegistryResult:
    return M1501HypothesisRegistry().infer(_request())


def _closed_error(result: ComplexActivityHypothesisRegistryResult, **updates: Any) -> ValueError:
    candidate = result.model_copy(update=updates)
    with pytest.raises(ValueError) as caught:
        candidate.result_is_closed()
    return caught.value


def test_nested_request_and_result_closure_reject_duplicate_ids() -> None:
    request = _request()
    duplicate_hypotheses = request.model_copy(update={"hypotheses": (request.hypotheses[0],) * 2})
    with pytest.raises(ValidationError, match="request hypothesis ids"):
        type(request).model_validate(duplicate_hypotheses.model_dump(mode="python"))

    result = _supported()
    duplicate_evaluations = (result.evaluations[0],) * 2
    assert "exactly one evaluation" in str(_closed_error(result, evaluations=duplicate_evaluations))

    finding = HypothesisFinding(
        finding_id="finding.one",
        code=HypothesisFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        message="Review the provisional ABI.",
        evidence=result.evidence,
    )
    assert "finding ids" in str(_closed_error(result, findings=(finding, finding)))


def test_result_closure_rejects_digest_id_evidence_and_unsafe_statuses() -> None:
    result = _supported()
    assert "derived from request digest" in str(_closed_error(result, result_id="result.invalid"))
    assert "evidence references" in str(
        _closed_error(result, evidence=(result.evidence[0].model_copy(update={"role": "input"}),))
    )
    assert "supported hypotheses" in str(_closed_error(result, human_review_required=True))
    assert "abstained result" in str(
        _closed_error(
            result,
            status=HypothesisStatus.ABSTAINED,
            registry=None,
            abstention_reason=None,
            support_decision=result.support_decision.model_copy(
                update={"status": SupportStatus.REVIEW_REQUIRED}
            ),
            human_review_required=True,
        )
    )


def test_expected_uncertainty_and_provenance_bind_all_required_dimensions() -> None:
    supported = expected_uncertainty(supported=True)
    abstained = expected_uncertainty(supported=False)
    assert supported.measurement.probability == 0.9
    assert abstained.measurement.probability is None
    assert len(supported.sensitivity_notes) == 1
    request = _request()
    provenance = expected_provenance(request, _supported().request_digest)
    assert len(provenance.control_decisions) == 7
    assert provenance.consent_decision_id == "decision.consent"
    assert provenance.input_digests[0] == _supported().request_digest


def test_replay_payload_digest_is_sensitive_to_semantic_changes() -> None:
    result = _supported()
    assert result_payload_digest(result) == result.result_digest
    changed = result.model_copy(
        update={
            "evaluations": (
                result.evaluations[0].model_copy(
                    update={"rationale": "Semantically changed rationale."}
                ),
            )
        }
    )
    assert result_payload_digest(changed) != result.result_digest
    assert result.falsification_evaluations[0].outcome is FalsificationOutcome.PASSED
