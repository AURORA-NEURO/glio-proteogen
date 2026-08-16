"""Evaluator and benchmark regression checks for M11-08."""

from typing import Final, cast

from evals.m11_08.benchmark import measure
from evals.m11_08.run import AUTHORITY_LINES, AUTHORITY_SHA256, evaluate

EXPECTED_SCENARIOS: Final = 9
EXPECTED_ITERATIONS: Final = 10


def test_m1108_evaluator_matrix_is_fixture_bound_and_green() -> None:
    report = evaluate()
    assert report["module"] == "GLIO-PROTEOGEN-M11-08"
    assert report["authority_sha256"] == AUTHORITY_SHA256
    assert report["authority_lines"] == AUTHORITY_LINES
    assert report["declared_scenarios"] == EXPECTED_SCENARIOS
    assert report["executed_scenarios"] == EXPECTED_SCENARIOS
    assert report["passed"] is True
    checks = cast("dict[str, bool]", report["checks"])
    assert all(checks.values())


def test_m1108_benchmark_stays_within_provisional_budget() -> None:
    report = measure()
    assert report["iterations"] == EXPECTED_ITERATIONS
    assert report["timed_boundary"] == "M1108MechanismEvidenceDossierService.execute_only"
    assert report["passed"] is True
