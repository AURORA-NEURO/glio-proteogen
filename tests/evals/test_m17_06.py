"""Evaluator matrix tests for provisional M17-06."""

import pytest
from evals.m17_06 import run as run_module
from evals.m17_06.benchmark import measure
from evals.m17_06.run import EXPECTED_CASE_IDS, evaluate

_BENCHMARK_ITERATIONS = 3


def test_locked_m1706_evaluator_passes_every_case() -> None:
    report = evaluate()
    assert report["passed"] is True
    assert report["declared_cases"] == len(EXPECTED_CASE_IDS)
    assert report["executed_cases"] == len(EXPECTED_CASE_IDS)
    assert report["passed_cases"] == len(EXPECTED_CASE_IDS)


def test_locked_m1706_benchmark_stays_within_provisional_budget() -> None:
    report = measure(_BENCHMARK_ITERATIONS)
    assert report["passed"] is True
    assert report["iterations"] == _BENCHMARK_ITERATIONS


def test_benchmark_rejects_invalid_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        measure(0)


def test_evaluator_cli_main_returns_success(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("sys.argv", ["m17_06"])
    assert run_module.main() == 0
    assert '"passed": true' in capsys.readouterr().out
