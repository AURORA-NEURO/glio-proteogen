"""Evaluator and benchmark entrypoint coverage for provisional M24 lanes."""

from __future__ import annotations

from evals.m24_02.benchmark import run as run_m2402_benchmark
from evals.m24_02.evaluator import run_matrix as run_m2402_matrix
from evals.m24_04.benchmark import run as run_m2404_benchmark
from evals.m24_04.evaluator import run_matrix as run_m2404_matrix
from evals.m24_06.benchmark import run as run_m2406_benchmark
from evals.m24_06.evaluator import run_matrix as run_m2406_matrix

_SMOKE_ITERATIONS = 2


def test_all_provisional_m24_evaluators_pass() -> None:
    for run_matrix in (run_m2402_matrix, run_m2404_matrix, run_m2406_matrix):
        report = run_matrix()
        assert report["passed"] is True
        assert all(report["scenarios"].values())
        assert str(report["supported_result_digest"]).startswith("sha256:")


def test_all_provisional_m24_benchmarks_are_bounded() -> None:
    for run_benchmark in (run_m2402_benchmark, run_m2404_benchmark, run_m2406_benchmark):
        report = run_benchmark(_SMOKE_ITERATIONS)
        assert report["iterations"] == _SMOKE_ITERATIONS
        assert report["min_ns"] <= report["median_ns"] <= report["max_ns"]
        assert report["p95_ns"] <= report["max_ns"]
