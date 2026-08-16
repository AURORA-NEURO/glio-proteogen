"""Runtime, replay, and safe-failure tests for M25-07."""

from __future__ import annotations

import pytest
from evals.m25_07.fixture import build_request, denied_request

from glio_proteogen.contracts.m25_07 import EvaluationStatus, OperationalStatus, result_identifier
from glio_proteogen.modules.c21_reference_material import (
    m25_07_human_factors_operational_evaluator as m2507,
)

_UNCERTAINTY_DIMENSIONS = 8


def test_supported_evaluation_is_deterministic_and_replayable() -> None:
    request = build_request()
    engine = m2507.M2507HumanFactorsEngine()
    first = engine.generate(request)
    second = engine.generate(request)

    assert first.status is EvaluationStatus.EVALUATED
    assert first.report is not None
    assert first.result_digest == second.result_digest
    assert first.result_id == result_identifier(request, "evaluated")
    assert engine.replay(first).result_digest == first.result_digest
    assert len(first.uncertainty.model_dump()) == _UNCERTAINTY_DIMENSIONS


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"metric_status": OperationalStatus.FAIL}, "metric"),
        ({"fallback_status": OperationalStatus.FAIL}, "fallback"),
        ({"fallback_available": False}, "fallback"),
    ],
)
def test_non_passing_operational_controls_abstain(
    kwargs: dict[str, object],
    code: str,
) -> None:
    result = m2507.M2507HumanFactorsEngine().generate(build_request(**kwargs))

    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.support_decision.status.value == "review_required"
    assert any(finding.finding_id.startswith(f"finding.{code}") for finding in result.findings)
    assert result.human_review_required is True


def test_denied_control_fails_before_execution() -> None:
    with pytest.raises(m2507.M2507AuthorizationError, match="accepted configuration"):
        m2507.M2507HumanFactorsEngine().generate(denied_request())


def test_replay_rejects_tampered_digest() -> None:
    result = m2507.M2507HumanFactorsEngine().generate(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})

    with pytest.raises(m2507.M2507ReplayError):
        m2507.M2507HumanFactorsEngine().replay(tampered)


def test_service_and_plugin_require_validated_submission() -> None:
    service = m2507.M2507Service()
    plugin = m2507.M2507Plugin(service)
    token = plugin.validate(m2507.HumanFactorsSubmission(build_request()))

    assert plugin.run(token).result_digest == service.execute(build_request()).result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_strict_json_path_is_parse_once() -> None:
    plugin = m2507.M2507Plugin(m2507.M2507Service())
    token = plugin.validate(m2507.HumanFactorsSubmission(build_request().model_dump_json()))

    assert plugin.run(token).status is EvaluationStatus.EVALUATED
