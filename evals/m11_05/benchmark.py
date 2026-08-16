"""Benchmark wrapper for the M11-05 public operation."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter_ns

from evals.m11_05.run import build_request
from glio_proteogen.modules.c11_protein_native_subtype.m11_05_longitudinal_evolution import (
    M1105Service,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


class InvalidBenchmarkIterationsError(ValueError):
    """Benchmark iteration count must be positive."""

    def __init__(self) -> None:
        super().__init__("iterations must be positive")


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    iterations: int
    mean_ns: int
    median_ns: int
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(0.95 * len(ordered))))
    return ordered[index]


def run_benchmark(iterations: int = 10) -> BenchmarkReport:
    if iterations < 1:
        raise InvalidBenchmarkIterationsError
    service = M1105Service()
    request = build_request()
    service.execute(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        service.execute(request)
        samples.append(perf_counter_ns() - started)
    mean = int(statistics.fmean(samples))
    p95 = _p95(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M11-05",
        iterations=iterations,
        mean_ns=mean,
        median_ns=int(statistics.median(samples)),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_benchmark(arguments.iterations)
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


__all__ = ["BenchmarkReport", "main", "run_benchmark"]


if __name__ == "__main__":
    raise SystemExit(main())
