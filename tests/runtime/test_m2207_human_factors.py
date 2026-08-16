"""Runtime and replay tests for provisional M22-07."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m22_07 import (
    EvaluationStatus,
    OperationalStatus,
    ProteinRnaDiscordanceHumanFactorsResult,
)
from glio_proteogen.modules.c21_reference_material import (
    m22_07_human_factors_operational_evaluator as m2207,
)
from tests.adversarial.test_m2207_contract import _request


def test_runtime_evaluates_supported_operational_material_deterministically() -> None:
    engine = m2207.M2207OperationalEngine()
    first = engine.generate(_request())
    second = engine.generate(_request())

    assert first.status is EvaluationStatus.EVALUATED
    assert first.report is not None
    assert first.result_id == second.result_id
    assert first.result_digest == second.result_digest
    assert first.human_review_required is True
    assert engine.replay(first).result_digest == first.result_digest


def test_runtime_abstains_when_operational_dimension_is_not_evaluable() -> None:
    request = _request().model_dump(mode="python")
    request["metrics"][0]["status"] = OperationalStatus.NOT_EVALUABLE
    engine = m2207.M2207OperationalEngine()
    result = engine.generate(request)

    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"
    assert engine.replay(result).status is EvaluationStatus.ABSTAINED


def test_runtime_exposes_metric_failure_without_turning_it_into_abstention() -> None:
    request = _request().model_dump(mode="python")
    request["metrics"][3]["observed_value"] = 2.0
    request["metrics"][3]["target_value"] = 1.0
    request["metrics"][3]["tolerance"] = 0.1
    request["metrics"][3]["status"] = OperationalStatus.FAIL

    result = m2207.M2207OperationalEngine().generate(request)

    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.findings
    assert result.findings[0].code.value == "latency_failure"


def test_runtime_fails_closed_before_validation_on_denied_control() -> None:
    request = _request().model_dump(mode="python")
    request["context"]["references"]["consent"]["state"] = "withheld"

    with pytest.raises(m2207.M2207AuthorizationError):
        m2207.M2207OperationalEngine().generate(request)


def test_runtime_rejects_tampered_result_digest() -> None:
    engine = m2207.M2207OperationalEngine()
    result = engine.generate(_request())
    tampered: ProteinRnaDiscordanceHumanFactorsResult = result.model_copy(
        update={"result_digest": "sha256:" + ("f" * 64)}
    )

    with pytest.raises(m2207.M2207ReplayError, match="payload digest"):
        engine.replay(tampered)
