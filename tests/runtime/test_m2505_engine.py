"""Runtime, replay, and safe-failure tests for M25-05."""

from __future__ import annotations

from typing import Any

import pytest
from evals.m25_05.fixture import build_request, denied_request

from glio_proteogen.contracts.m25_05 import (
    CoverageStatus,
    EquityStatus,
    EvaluationStatus,
    result_identifier,
)
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.engine import (
    M2505AuthorizationError,
    M2505ReplayError,
    M2505SubgroupEquityEngine,
    evaluate_proteotype_subgroup_equity,
)
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.plugin import (
    M2505Plugin,
    SubgroupEquitySubmission,
)
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.service import (
    M2505Service,
)

_UNCERTAINTY_DIMENSIONS = 8


def test_supported_evaluation_is_deterministic_and_replayable() -> None:
    request = build_request()
    engine = M2505SubgroupEquityEngine()
    first = engine.generate(request)
    second = evaluate_proteotype_subgroup_equity(request)

    assert first.status is EvaluationStatus.EVALUATED
    assert first.report is not None
    assert first.result_digest == second.result_digest
    assert first.result_id == result_identifier(request, "evaluated")
    assert engine.replay(first).result_digest == first.result_digest
    assert len(first.uncertainty.model_dump()) == _UNCERTAINTY_DIMENSIONS


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"performance_status": EquityStatus.BELOW_FLOOR}, "safety_floor_breach"),
        ({"coverage_status": CoverageStatus.LIMITED}, "coverage_limited"),
        ({"coverage_status": CoverageStatus.UNSUPPORTED}, "rare_context_unsupported"),
    ],
)
def test_non_passing_subgroup_controls_abstain(
    kwargs: dict[str, Any],
    code: str,
) -> None:
    result = M2505SubgroupEquityEngine().generate(build_request(**kwargs))

    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.support_decision.status.value == "review_required"
    assert any(finding.code.value == code for finding in result.findings)
    assert result.human_review_required is True


def test_calibration_failure_abstains_without_negative_inference() -> None:
    result = M2505SubgroupEquityEngine().generate(
        build_request(calibration_status=EvaluationStatus.ABSTAINED)
    )

    assert result.status is EvaluationStatus.ABSTAINED
    assert all(finding.code.value == "calibration_failure" for finding in result.findings)
    assert result.abstention_reason is not None
    assert "negative" not in result.abstention_reason.lower()


def test_denied_control_fails_before_execution() -> None:
    with pytest.raises(M2505AuthorizationError, match="accepted configuration"):
        M2505SubgroupEquityEngine().generate(denied_request())


def test_replay_rejects_tampered_digest() -> None:
    result = M2505SubgroupEquityEngine().generate(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})

    with pytest.raises(M2505ReplayError):
        M2505SubgroupEquityEngine().replay(tampered)


def test_service_and_plugin_require_validated_submission() -> None:
    service = M2505Service()
    plugin = M2505Plugin(service)
    token = plugin.validate(SubgroupEquitySubmission(build_request()))

    assert plugin.run(token).result_digest == service.execute(build_request()).result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_strict_json_path_is_parse_once() -> None:
    service = M2505Service()
    plugin = M2505Plugin(service)
    token = plugin.validate(SubgroupEquitySubmission(build_request().model_dump_json()))

    assert plugin.run(token).status is EvaluationStatus.EVALUATED
