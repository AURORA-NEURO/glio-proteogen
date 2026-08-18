"""Evaluator and benchmark checks for the research pipeline."""

from __future__ import annotations

from typing import cast

import pytest
from evals.research_proteomics.run import run_benchmark, run_evaluator


def test_locked_research_pipeline_evaluator() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert cast("int", report["declared"]) == cast("int", report["executed"]) == 7
    assert len(cast("str", report["fixture_sha256"])) == 64


def test_research_pipeline_benchmark_is_deterministic() -> None:
    report = run_benchmark(3)
    assert cast("int", report["iterations"]) == 3
    assert cast("float", report["mean_ns"]) > 0
    assert cast("int", report["median_ns"]) > 0
    assert cast("int", report["p95_ns"]) > 0
    assert len(cast("str", report["result_digest"])) == 64


def test_research_pipeline_benchmark_rejects_empty_iterations() -> None:
    with pytest.raises(ValueError):
        run_benchmark(0)
