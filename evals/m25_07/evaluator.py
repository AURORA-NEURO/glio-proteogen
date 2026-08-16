"""Executable M25-07 scenario matrix and adversarial evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from evals.m25_07.fixture import build_request, denied_request
from glio_proteogen.contracts.m25_07 import OperationalStatus
from glio_proteogen.modules.c21_reference_material import (
    m25_07_human_factors_operational_evaluator as m2507,
)

_ENGINE: Final = m2507.M2507HumanFactorsEngine()
_METRIC_DIMENSIONS = 7
_FALLBACK_DIMENSIONS = 3


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    passed: bool
    status: str
    detail: str


def _supported() -> ScenarioResult:
    result = _ENGINE.generate(build_request())
    return ScenarioResult(
        name="supported_operational_evaluation",
        passed=result.status.value == "evaluated" and result.report is not None,
        status=result.status.value,
        detail="all seven operational dimensions and fallback paths evaluated",
    )


def _metric_abstention() -> ScenarioResult:
    result = _ENGINE.generate(build_request(metric_status=OperationalStatus.FAIL))
    return ScenarioResult(
        name="metric_failure_abstention",
        passed=result.status.value == "abstained" and result.report is None,
        status=result.status.value,
        detail="non-passing operational metric is withheld for review",
    )


def _fallback_abstention() -> ScenarioResult:
    result = _ENGINE.generate(build_request(fallback_status=OperationalStatus.FAIL))
    return ScenarioResult(
        name="fallback_failure_abstention",
        passed=result.status.value == "abstained" and result.report is None,
        status=result.status.value,
        detail="non-passing recovery/fallback path is explicit",
    )


def _unavailable_abstention() -> ScenarioResult:
    result = _ENGINE.generate(build_request(fallback_available=False))
    return ScenarioResult(
        name="unavailable_fallback_abstention",
        passed=result.status.value == "abstained",
        status=result.status.value,
        detail="unavailable fallback cannot appear as a passing operation",
    )


def _denied() -> ScenarioResult:
    try:
        _ENGINE.generate(denied_request())
    except m2507.M2507AuthorizationError:
        return ScenarioResult(
            name="denied_control", passed=True, status="rejected", detail="preflight failed closed"
        )
    return ScenarioResult(
        name="denied_control", passed=False, status="executed", detail="denied control executed"
    )


def _replay() -> ScenarioResult:
    result = _ENGINE.generate(build_request())
    replayed = _ENGINE.replay(result)
    return ScenarioResult(
        name="canonical_replay",
        passed=replayed.result_digest == result.result_digest,
        status="verified",
        detail="result and request digests replay exactly",
    )


def _determinism() -> ScenarioResult:
    first = _ENGINE.generate(build_request())
    second = _ENGINE.generate(build_request())
    return ScenarioResult(
        name="deterministic_digest",
        passed=first.result_id == second.result_id and first.result_digest == second.result_digest,
        status="stable",
        detail="same canonical input produces same identity and digest",
    )


def _tamper() -> ScenarioResult:
    result = _ENGINE.generate(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})
    try:
        _ENGINE.replay(tampered)
    except m2507.M2507ReplayError:
        return ScenarioResult(
            name="tamper_replay", passed=True, status="rejected", detail="digest tamper detected"
        )
    return ScenarioResult(
        name="tamper_replay", passed=False, status="accepted", detail="tamper was accepted"
    )


def _all_dimensions() -> ScenarioResult:
    result = _ENGINE.generate(build_request())
    report = result.report
    return ScenarioResult(
        name="dimension_and_fallback_closure",
        passed=(
            report is not None
            and len(report.metrics) == _METRIC_DIMENSIONS
            and len(report.fallbacks) == _FALLBACK_DIMENSIONS
        ),
        status=result.status.value,
        detail="seven metrics and three mandatory fallback scenarios are present",
    )


def run_scenarios() -> tuple[ScenarioResult, ...]:
    """Run the locked eight-scenario M25-07 evaluator matrix."""

    return (
        _supported(),
        _metric_abstention(),
        _fallback_abstention(),
        _unavailable_abstention(),
        _denied(),
        _replay(),
        _determinism(),
        _all_dimensions(),
    )


def run_adversarial() -> tuple[ScenarioResult, ...]:
    """Repeat hostile controls as an executable release gate."""

    return (_denied(), _tamper(), _metric_abstention(), _unavailable_abstention())


def evaluate() -> bool:
    """Return whether every locked and hostile scenario passes."""

    return all(result.passed for result in (*run_scenarios(), *run_adversarial()))


__all__ = ["ScenarioResult", "evaluate", "run_adversarial", "run_scenarios"]
