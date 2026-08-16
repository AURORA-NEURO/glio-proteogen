"""Evaluator and benchmark checks for M16-07."""

# ruff: noqa: PLR2004

from __future__ import annotations

from typing import cast

import pytest
from evals.m16_07.benchmark import measure
from evals.m16_07.run import evaluate


def test_m1607_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report["passed"] is True
    assert report["executed_cases"] == 10
    checks = cast("list[dict[str, object]]", report["checks"])
    assert all(item["passed"] is True for item in checks)


def test_m1607_benchmark_stays_within_provisional_budgets() -> None:
    report = measure(iterations=3)
    assert report["passed"] is True
    assert cast("int", report["mean_ns"]) <= cast("int", report["mean_budget_ns"])
    assert cast("int", report["p95_ns"]) <= cast("int", report["p95_budget_ns"])


def test_m1607_benchmark_rejects_nonpositive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        measure(0)
