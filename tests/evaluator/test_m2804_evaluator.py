"""Executable M28-04 evaluator assertions."""

from pathlib import Path

from evals.m28_04 import benchmark, run
from evals.m28_04.benchmark import ITERATIONS, run_benchmark
from evals.m28_04.run import EXPECTED_CHECK_COUNT, run_evaluator


def test_m2804_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert len(report.checks) == EXPECTED_CHECK_COUNT
    assert report.passed
    assert all(check.passed for check in report.checks)


def test_m2804_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()
    assert report.iterations == ITERATIONS
    assert report.passed
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns


def test_m2804_evaluator_and_benchmark_write_machine_reports(tmp_path: Path) -> None:
    evaluator_path = tmp_path / "evaluation.json"
    benchmark_path = tmp_path / "benchmark.json"
    assert run.main(["--output", str(evaluator_path)]) == 0
    assert benchmark.main(["--output", str(benchmark_path)]) == 0
    assert '"passed": true' in evaluator_path.read_text(encoding="utf-8")
    assert '"passed": true' in benchmark_path.read_text(encoding="utf-8")
