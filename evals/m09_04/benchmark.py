"""Deterministic benchmark for the M09-04 posterior boundary."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from tests.modules.c09_complex_stoichiometry.test_m09_04_estimator import _request

from glio_proteogen.modules.c09_complex_stoichiometry.m09_04_probabilistic_estimator import (
    M0904ProbabilisticEstimator,
)

DEFAULT_ITERATIONS = 10
MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    mean_ns: float
    median_ns: float
    p95_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    prior_count: int
    constraint_count: int
    feature_count: int
    passed: bool


def benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    if iterations <= 0:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = _request("stable_support", "soft stability")
    engine = M0904ProbabilisticEstimator()
    expected = engine.build(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        built = engine.build(request)
        samples.append(perf_counter_ns() - started)
        if built.canonical_bytes != expected.canonical_bytes:
            raise RuntimeError("M09-04 result was not deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M09-04",
        contract_version="0.1.0-provisional",
        workload="probabilistic posterior estimation with explicit soft diagnostics",
        timed_boundary="M0904ProbabilisticEstimator.build",
        iterations=iterations,
        mean_ns=mean,
        median_ns=median(samples),
        p95_ns=p95,
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        prior_count=len(request.configuration.priors),
        constraint_count=len(request.configuration.constraints),
        feature_count=len(request.source_artifacts),
        passed=mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = benchmark(args.iterations)
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["BenchmarkReport", "benchmark", "main"]
