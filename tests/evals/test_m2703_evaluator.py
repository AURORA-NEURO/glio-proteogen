"""Evaluator and benchmark gates for M27-03."""

from __future__ import annotations

import pytest
from benchmarks.m27_03_reproducible_pipeline import run
from evals.m27_03.run import run_evaluation

_SCENARIO_COUNT = 5
_BENCHMARK_ITERATIONS = 3


def test_m2703_evaluator_covers_execution_abstention_replay_and_plugin_parity() -> None:
    report = run_evaluation()
    assert report["supported_executed"] is True
    assert report["supported_replay"] is True
    assert report["rejected_abstained"] is True
    assert report["rejected_no_package"] is True
    assert report["plugin_parity"] is True
    assert report["scenario_count"] == _SCENARIO_COUNT


def test_m2703_benchmark_reports_budget_and_rejects_empty_runs() -> None:
    report = run(_BENCHMARK_ITERATIONS)
    assert report["moduleId"] == "GLIO-PROTEOGEN-M27-03"
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["budgetPassed"] is True
    with pytest.raises(ValueError, match="iterations must be positive"):
        run(0)
