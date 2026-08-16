"""Benchmark contract and deterministic output checks for M06-06."""

from __future__ import annotations

import pytest
from evals.m06_06.benchmark import run_benchmark

from glio_proteogen.contracts.m06_06 import (
    M0606_BENCHMARK_ITERATIONS,
    M0606_BENCHMARK_WARMUPS,
)

_EXPECTED_ITERATIONS = 25
_EXPECTED_WARMUPS = 1

pytestmark = pytest.mark.integration


def test_benchmark_runs_exact_frozen_workload() -> None:
    report = run_benchmark()
    assert report["iterations"] == M0606_BENCHMARK_ITERATIONS == _EXPECTED_ITERATIONS
    assert report["warmups"] == M0606_BENCHMARK_WARMUPS == _EXPECTED_WARMUPS
    assert report["all_digests_equal"] is True
    assert report["all_abstained"] is True
    assert report["mean_budget_pass"] is True
    assert report["p95_budget_pass"] is True
