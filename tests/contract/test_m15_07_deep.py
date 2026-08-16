"""Adversarial closure tests for M15-07 results and control semantics."""

# ruff: noqa: E501

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m15_07 import (
    ComplexActivityPlausibilityAdjudicationResult,
    ControlOutcome,
    PlausibilityGrade,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_07_plausibility_negative_control_adjudicator import (
    M1507PlausibilityAdjudicator,
)
from tests.modules.c15_longitudinal_recurrence.test_m15_07_engine import _request


def test_result_digest_request_binding_and_evidence_role_are_closed() -> None:
    result = M1507PlausibilityAdjudicator().adjudicate(_request())
    with pytest.raises(ValidationError, match="request digest"):
        ComplexActivityPlausibilityAdjudicationResult.model_validate(
            result.model_dump(mode="python") | {"request_digest": sha256_digest("wrong")}
        )
    forged_evidence = result.evidence[0].model_copy(update={"role": "counter_evidence"})
    with pytest.raises(ValidationError, match="requires evidence"):
        ComplexActivityPlausibilityAdjudicationResult.model_validate(
            result.model_dump(mode="python") | {"evidence": (forged_evidence,)}
        )


def test_duplicate_finding_and_blocked_adjudicated_result_are_rejected() -> None:
    result = M1507PlausibilityAdjudicator().adjudicate(_request())
    duplicate = result.findings[0]
    with pytest.raises(ValidationError, match="finding ids"):
        ComplexActivityPlausibilityAdjudicationResult.model_validate(
            result.model_dump(mode="python") | {"findings": (*result.findings, duplicate)}
        )
    failed = result.evaluations[0].model_copy(update={"outcome": ControlOutcome.FAILED})
    with pytest.raises(ValidationError, match="adjudicated result"):
        ComplexActivityPlausibilityAdjudicationResult.model_validate(
            result.model_dump(mode="python") | {"evaluations": (failed, *result.evaluations[1:])}
        )


def test_abstained_result_cannot_carry_grade_or_skip_review() -> None:
    result = M1507PlausibilityAdjudicator().adjudicate(_request("negative_control_gate"))
    with pytest.raises(ValidationError, match="abstained result"):
        ComplexActivityPlausibilityAdjudicationResult.model_validate(
            result.model_dump(mode="python")
            | {"grade": PlausibilityGrade.LOW, "human_review_required": False}
        )
