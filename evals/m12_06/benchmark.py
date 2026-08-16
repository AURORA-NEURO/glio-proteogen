"""Benchmark the public M12-06 simulator boundary."""

# Long module paths and explicit benchmark failure messages are intentional.
# ruff: noqa: E501,TRY003

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns
from typing import Final

from evals.m12_06.run import build_request
from glio_proteogen.contracts.m12_06 import M1206_CONTRACT_VERSION, M1206_MODULE_ID
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator import (
    M1206Service,
)

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    iterations: int
    request_digest: str
    result_digest: str
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


def run_benchmark(iterations: int = ITERATIONS) -> BenchmarkReport:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    request = build_request()
    service = M1206Service()
    warm = service.execute(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = service.execute(request)
        samples.append(perf_counter_ns() - started)
        if result != warm:
            raise RuntimeError("M12-06 benchmark execution is nondeterministic")
    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    return BenchmarkReport(
        module_id=M1206_MODULE_ID,
        contract_version=M1206_CONTRACT_VERSION,
        iterations=iterations,
        request_digest=warm.request_digest,
        result_digest=warm.result_digest,
        mean_ns=fmean(samples),
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=fmean(samples) <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iterations", type=int, default=ITERATIONS)
    arguments = parser.parse_args(argv)
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
