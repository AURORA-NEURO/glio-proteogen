"""Benchmark the public M27-04 gateway publication boundary."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns
from typing import Final

from evals.m27_04.fixture import build_request
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.engine import (
    M2704GatewayEngine,
)

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 500_000_000
P95_BUDGET_NS: Final = 750_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Deterministic benchmark evidence with explicit budgets."""

    module_id: str
    workload: str
    iterations: int
    request_digest: str
    result_digest: str
    mean_ns: float
    median_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


class NonDeterministicBenchmarkError(RuntimeError):
    """The timed publication disagreed with its warmed canonical result."""


def run_benchmark() -> BenchmarkReport:
    """Warm once, then time exactly ten deterministic engine publications."""

    request = build_request()
    engine = M2704GatewayEngine()
    warmup = engine.publish(request)
    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = perf_counter_ns()
        result = engine.publish(request)
        samples.append(perf_counter_ns() - started)
        if result != warmup:
            raise NonDeterministicBenchmarkError
    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M27-04",
        workload="caller_declared_complex_activity_gateway_request",
        iterations=ITERATIONS,
        request_digest=sha256_digest(request.model_dump(mode="json")),
        result_digest=warmup.result_digest,
        mean_ns=mean,
        median_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    )


def main(argv: list[str] | None = None) -> int:
    """Print benchmark evidence and return a budget status."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run_benchmark()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


__all__ = ["BenchmarkReport", "main", "run_benchmark"]


if __name__ == "__main__":
    raise SystemExit(main())
