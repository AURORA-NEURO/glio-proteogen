"""Evaluator and benchmark tests for M20-02."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from evals.m20_02 import benchmark, run
from evals.m20_02.benchmark import run_benchmark
from evals.m20_02.fixture import build_synthetic_request
from evals.m20_02.run import run_evaluation

from glio_proteogen.contracts.m20_02 import AlignmentObservationStatus

if TYPE_CHECKING:
    from pathlib import Path

SCENARIO_COUNT = 3


def test_m20_02_evaluator_matrix_and_replay() -> None:
    report = run_evaluation()
    assert report["scenario_count"] == SCENARIO_COUNT
    assert report["passed_count"] == SCENARIO_COUNT
    assert report["replay_count"] == SCENARIO_COUNT
    assert report["passed"] is True


def test_m20_02_locked_benchmark_is_within_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report["iterations"] == SCENARIO_COUNT
    assert cast("float", report["mean_ns"]) < cast("int", report["budget_mean_ns"])
    assert cast("int", report["p95_ns"]) < cast("int", report["budget_p95_ns"])
    assert report["passed"] is True
    assert cast("str", report["request_digest"]).startswith("sha256:")
    assert cast("str", report["result_digest"]).startswith("sha256:")


def test_m20_02_synthetic_fixture_and_factory_compatibility() -> None:
    conflicted = build_synthetic_request(status=AlignmentObservationStatus.CONFLICTED)
    assert {item.status for item in conflicted.observations} == {
        AlignmentObservationStatus.CONFLICTED
    }
    assert run_evaluation(build_synthetic_request)["passed"] is True
    assert run_benchmark(build_synthetic_request, iterations=1)["passed"] is True


def test_m20_02_command_entrypoints_write_self_contained_reports(tmp_path: Path) -> None:
    evaluation_path = tmp_path / "evaluation.json"
    benchmark_path = tmp_path / "benchmark.json"

    assert run.main(["--output", str(evaluation_path)]) == 0
    assert benchmark.main(["--iterations", "2", "--output", str(benchmark_path)]) == 0
    assert json.loads(evaluation_path.read_text(encoding="utf-8"))["passed"] is True
    assert json.loads(benchmark_path.read_text(encoding="utf-8"))["passed"] is True


def test_m20_02_benchmark_rejects_nonpositive_iterations() -> None:
    with pytest.raises(ValueError, match="iterations must be positive"):
        run_benchmark(iterations=0)
