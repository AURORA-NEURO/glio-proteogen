"""Evaluator and benchmark assertions for M19-08."""

import json
from pathlib import Path

import pytest
from evals.m19_08 import benchmark, run
from evals.m19_08.benchmark import run_benchmark
from evals.m19_08.run import evaluate


def test_m1908_evaluator_meets_adversarial_target() -> None:
    report = evaluate()

    assert report.passed is True
    assert report.adversarial_coverage_percent >= report.target_percent
    assert report.adversarial_passed_count == report.adversarial_case_count
    assert all(check.passed for check in report.checks)


def test_m1908_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()

    assert report.passed is True
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns
    assert report.request_digest.startswith("sha256:")
    assert report.result_digest.startswith("sha256:")


def test_m1908_cli_evidence_writers_emit_closed_json(tmp_path: Path) -> None:
    output = tmp_path / "evaluation.json"
    benchmark_output = tmp_path / "benchmark.json"
    assert run.main(["--output", str(output)]) == 0
    assert benchmark.main(["--output", str(benchmark_output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is True
    assert json.loads(benchmark_output.read_text(encoding="utf-8"))["passed"] is True


def test_m1908_unknown_evaluator_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown M19-08"):
        run._scenario("unknown")
