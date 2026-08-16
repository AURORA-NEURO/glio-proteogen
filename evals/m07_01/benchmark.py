"""Deterministic M07-01 formal-state validation benchmark wrapper."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from tests.modules.c07_copy_number.test_m07_01_formal_state import _request

from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema import (
    M0701FormalStateEngine,
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
    feature_count: int
    invariant_count: int
    passed: bool


def benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    if isinstance(iterations, bool) or iterations <= 0:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = _request()
    engine = M0701FormalStateEngine()
    expected = engine.execute(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        built = engine.execute(request)
        samples.append(perf_counter_ns() - started)
        if built.canonical_bytes != expected.canonical_bytes:
            raise RuntimeError("formal-state result was not deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M07-01",
        contract_version="0.1.0-provisional",
        workload="one scalar copy-number feature with one hard invariant",
        timed_boundary="M0701FormalStateEngine.execute",
        iterations=iterations,
        mean_ns=mean,
        median_ns=median(samples),
        p95_ns=p95,
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        feature_count=len(request.state_schema.features),
        invariant_count=len(request.state_schema.invariants),
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
