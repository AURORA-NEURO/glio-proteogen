"""Evaluator and benchmark checks for M15-07."""

# ruff: noqa: PLR2004

from __future__ import annotations

from typing import cast

import pytest
from evals.m15_07.benchmark import measure
from evals.m15_07.run import evaluate


def test_m1507_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report["passed"] is True
    assert report["executed_cases"] == 9
    checks = cast("list[dict[str, object]]", report["checks"])
    assert all(item["passed"] is True for item in checks)


def test_m1507_benchmark_stays_within_provisional_budgets() -> None:
    report = measure(iterations=3)
    assert report["passed"] is True
    mean_ns = cast("int", report["mean_ns"])
    mean_budget_ns = cast("int", report["mean_budget_ns"])
    p95_ns = cast("int", report["p95_ns"])
    p95_budget_ns = cast("int", report["p95_budget_ns"])
    assert mean_ns <= mean_budget_ns
    assert p95_ns <= p95_budget_ns


def test_m1507_benchmark_rejects_nonpositive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        measure(0)
