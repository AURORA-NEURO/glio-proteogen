"""Executable M25-05 scenario matrix and adversarial evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from evals.m25_05.fixture import build_request, denied_request
from glio_proteogen.contracts.m25_05 import (
    CoverageStatus,
    EquityStatus,
    EvaluationStatus,
    result_payload_digest,
)
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.engine import (
    M2505AuthorizationError,
    M2505ReplayError,
    M2505SubgroupEquityEngine,
)

_ENGINE: Final = M2505SubgroupEquityEngine()


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    passed: bool
    status: str
    detail: str


def _supported() -> ScenarioResult:
    result = _ENGINE.generate(build_request())
    return ScenarioResult(
        "supported_evaluated",
        result.status is EvaluationStatus.EVALUATED and result.report is not None,
        result.status.value,
        "all eight subgroup dimensions evaluated",
    )


def _floor_abstention() -> ScenarioResult:
    result = _ENGINE.generate(build_request(performance_status=EquityStatus.BELOW_FLOOR))
    return ScenarioResult(
        "equity_floor_abstention",
        result.status is EvaluationStatus.ABSTAINED
        and any(finding.code.value == "safety_floor_breach" for finding in result.findings),
        result.status.value,
        "below-floor declaration is withheld for review",
    )


def _limited_coverage() -> ScenarioResult:
    result = _ENGINE.generate(build_request(coverage_status=CoverageStatus.LIMITED))
    return ScenarioResult(
        "limited_coverage_abstention",
        result.status is EvaluationStatus.ABSTAINED,
        result.status.value,
        "limited coverage cannot be promoted to an equity conclusion",
    )


def _unsupported_coverage() -> ScenarioResult:
    result = _ENGINE.generate(build_request(coverage_status=CoverageStatus.UNSUPPORTED))
    return ScenarioResult(
        "unsupported_coverage_abstention",
        result.status is EvaluationStatus.ABSTAINED,
        result.status.value,
        "unsupported rare context remains explicit",
    )


def _calibration_abstention() -> ScenarioResult:
    result = _ENGINE.generate(build_request(calibration_status=EvaluationStatus.ABSTAINED))
    return ScenarioResult(
        "calibration_abstention",
        result.status is EvaluationStatus.ABSTAINED,
        result.status.value,
        "calibration control is required",
    )


def _replay() -> ScenarioResult:
    result = _ENGINE.generate(build_request())
    replayed = _ENGINE.replay(result)
    return ScenarioResult(
        "canonical_replay",
        replayed.result_digest == result.result_digest,
        "verified",
        "result and request digests replay exactly",
    )


def _denied() -> ScenarioResult:
    try:
        _ENGINE.generate(denied_request())
    except M2505AuthorizationError:
        return ScenarioResult(
            name="denied_control", passed=True, status="rejected", detail="preflight failed closed"
        )
    return ScenarioResult(
        name="denied_control",
        passed=False,
        status="executed",
        detail="denied control was not rejected",
    )


def _determinism() -> ScenarioResult:
    first = _ENGINE.generate(build_request())
    second = _ENGINE.generate(build_request())
    return ScenarioResult(
        "deterministic_digest",
        first.result_id == second.result_id and first.result_digest == second.result_digest,
        "stable",
        "same canonical input produces same identity and digest",
    )


def _tamper() -> ScenarioResult:
    result = _ENGINE.generate(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})
    try:
        _ENGINE.replay(tampered)
    except M2505ReplayError:
        return ScenarioResult(
            name="tamper_replay", passed=True, status="rejected", detail="digest tamper detected"
        )
    return ScenarioResult(
        name="tamper_replay", passed=False, status="accepted", detail="tamper was accepted"
    )


def _semantic_tamper() -> ScenarioResult:
    result = _ENGINE.generate(build_request())
    assert result.report is not None
    forged = result.model_copy(
        update={"report": result.report.model_copy(update={"version": "1.0.1"})}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    try:
        _ENGINE.replay(forged)
    except M2505ReplayError:
        return ScenarioResult(
            name="semantic_tamper_replay",
            passed=True,
            status="rejected",
            detail="self-rehashed report mutation rejected by canonical regeneration",
        )
    return ScenarioResult(
        name="semantic_tamper_replay",
        passed=False,
        status="accepted",
        detail="self-rehashed report mutation was accepted",
    )


def run_scenarios() -> tuple[ScenarioResult, ...]:
    """Run the locked ten-scenario M25-05 evaluator matrix."""

    return (
        _supported(),
        _floor_abstention(),
        _limited_coverage(),
        _unsupported_coverage(),
        _calibration_abstention(),
        _replay(),
        _denied(),
        _determinism(),
        _tamper(),
        _semantic_tamper(),
    )


def run_adversarial() -> tuple[ScenarioResult, ...]:
    """Repeat hostile controls as an executable release gate."""

    return (
        _denied(),
        _tamper(),
        _semantic_tamper(),
        _unsupported_coverage(),
        _floor_abstention(),
    )


def evaluate() -> bool:
    """Return whether every locked and hostile scenario passes."""

    return all(result.passed for result in (*run_scenarios(), *run_adversarial()))


__all__ = ["ScenarioResult", "evaluate", "run_adversarial", "run_scenarios"]
