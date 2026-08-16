"""Deterministic benchmark for the M09-01 formal-state boundary."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from tests.modules.c09_complex_stoichiometry.test_m09_01_formal_state import _request

from glio_proteogen.contracts.m09_01 import (
    M0901_BENCHMARK_ITERATIONS,
    M0901_MEAN_BUDGET_NS,
    M0901_P95_BUDGET_NS,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    M0901Service,
)


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
    feature_count: int
    invariant_count: int
    passed: bool


def benchmark(iterations: int = M0901_BENCHMARK_ITERATIONS) -> BenchmarkReport:
    if iterations <= 0:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = _request()
    service = M0901Service()
    expected = service.execute(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        built = service.execute(request)
        samples.append(perf_counter_ns() - started)
        if built.canonical_bytes != expected.canonical_bytes:
            raise RuntimeError("M09-01 result was not deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M09-01",
        contract_version="0.1.0-provisional",
        workload="formal complex-activity schema and invariant validation",
        timed_boundary="M0901Service.execute",
        iterations=iterations,
        mean_ns=mean,
        median_ns=median(samples),
        p95_ns=p95,
        mean_budget_ns=M0901_MEAN_BUDGET_NS,
        p95_budget_ns=M0901_P95_BUDGET_NS,
        feature_count=len(request.values),
        invariant_count=len(request.state_schema.invariants),
        passed=mean <= M0901_MEAN_BUDGET_NS and p95 <= M0901_P95_BUDGET_NS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=M0901_BENCHMARK_ITERATIONS)
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
