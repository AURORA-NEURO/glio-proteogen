"""Evaluator and benchmark smoke tests for M21-06."""

import pytest
from evals.m21_06.benchmark import main as benchmark_main
from evals.m21_06.benchmark import run_benchmark
from evals.m21_06.evaluator import main as evaluator_main
from evals.m21_06.evaluator import run_evaluator


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"]
    assert all(report["checks"].values())


def test_benchmark_rejects_non_positive_iterations(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(0)
    report = run_benchmark(1)
    assert report["passed"] is True
    benchmark_main()
    evaluator_main()
    assert '"M21-06"' in capsys.readouterr().out
