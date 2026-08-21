"""M15-07 runtime, authorization, safe-failure, and replay tests."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

from typing import cast

import pytest

from glio_proteogen.contracts.m15_07 import (
    M1507_M1506_RESULT_MEDIA_TYPE,
    AdjudicateComplexActivityPlausibilityRequest,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, SupportStatus
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_07_plausibility_negative_control_adjudicator import (
    M1507AuthorizationError,
    M1507InferenceError,
    M1507PlausibilityAdjudicator,
    M1507ReplayVerificationError,
    adjudicate_complex_activity_plausibility,
    preflight_plausibility_authorization,
)
from tests.contract.test_m15_07_contract import _request as contract_request


def _request(
    label: str = "sensitivity", *, accepted: bool = True
) -> AdjudicateComplexActivityPlausibilityRequest:
    request = contract_request(accepted=accepted)
    sensitivity = ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1507": label}),
        media_type=M1507_M1506_RESULT_MEDIA_TYPE,
    )
    return AdjudicateComplexActivityPlausibilityRequest.model_validate(
        request.model_dump(mode="python") | {"sensitivity_result": sensitivity}
    )


def test_positive_adjudication_is_deterministic_and_replayable() -> None:
    engine = M1507PlausibilityAdjudicator()
    result = engine.adjudicate(_request())
    assert result.status is PlausibilityAdjudicationStatus.ADJUDICATED
    assert result.grade is not None
    assert result.grade.value == "high"
    assert all(item.outcome is ControlOutcome.PASSED for item in result.evaluations)
    assert result.conflicts == ()
    assert len(result.provenance.control_decisions) == 7
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.uncertainty.measurement.probability is None
    assert engine.verify(result) == result
    assert adjudicate_complex_activity_plausibility(_request()) == result


@pytest.mark.parametrize(
    ("label", "outcome"),
    [
        ("negative_control_gate", ControlOutcome.FAILED),
        ("unsupported_input", ControlOutcome.NOT_EVALUABLE),
        ("abstain_input", ControlOutcome.ABSTAINED),
    ],
)
def test_blocking_inputs_abstain_and_preserve_evaluations(
    label: str, outcome: ControlOutcome
) -> None:
    result = M1507PlausibilityAdjudicator().adjudicate(_request(label))
    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert result.grade is None
    assert result.human_review_required is True
    assert any(item.outcome is outcome for item in result.evaluations)
    assert result.abstention_reason is not None


def test_conflicts_remain_visible_and_block_promotion() -> None:
    result = M1507PlausibilityAdjudicator().adjudicate(_request("unresolved_conflict"))
    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert len(result.conflicts) == 1
    assert len(result.conflicts[0].competing_mechanisms) == 2
    assert any(item.code.value == "unresolved_conflict" for item in result.findings)


def test_prohibited_boundary_abstains() -> None:
    result = M1507PlausibilityAdjudicator().adjudicate(_request("kinase_activity"))
    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert any(item.code.value == "upstream_unsupported" for item in result.findings)


def test_authorization_fails_closed_for_denied_or_hostile_controls() -> None:
    denied = contract_request(accepted=False)
    with pytest.raises(M1507AuthorizationError, match="authorize"):
        preflight_plausibility_authorization(denied)
    with pytest.raises(M1507AuthorizationError, match="unavailable"):
        preflight_plausibility_authorization({"context": None})
    with pytest.raises(M1507AuthorizationError, match="unavailable"):
        preflight_plausibility_authorization(cast("object", []))


def test_invalid_request_and_tamper_are_rejected() -> None:
    engine = M1507PlausibilityAdjudicator()
    invalid_request = contract_request().model_dump(mode="python")
    invalid_request.pop("controls")
    with pytest.raises(M1507InferenceError):
        engine.adjudicate(invalid_request)
    result = engine.adjudicate(_request())
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    with pytest.raises(M1507ReplayVerificationError):
        engine.verify(tampered)
    assert engine.verify(result, replay=False) == result
