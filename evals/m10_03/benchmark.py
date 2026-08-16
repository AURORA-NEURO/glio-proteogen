"""Reproducible M10-03 benchmark over the public estimator boundary."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns
from typing import Final

from evals.m10_03.run import build_scenario_request
from glio_proteogen.contracts.m10_03 import (
    M1003_BENCHMARK_ITERATIONS,
    M1003_CONTRACT_VERSION,
    M1003_MEAN_BUDGET_NS,
    M1003_MODULE_ID,
    M1003_P95_BUDGET_NS,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator import (
    estimate_protein_rna_discordance_baseline,
)

ITERATIONS: Final = M1003_BENCHMARK_ITERATIONS
MIN_ITERATIONS: Final = 2
WARMUP_COUNT: Final = 1


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    warmup_count: int
    target_count: int
    request_digest: str
    result_digest: str
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    deterministic: bool
    passed: bool


class InvalidBenchmarkIterationsError(ValueError):
    """Raised when a benchmark cannot produce a percentile estimate."""


def run_benchmark(iterations: int = ITERATIONS) -> BenchmarkReport:
    if iterations < MIN_ITERATIONS:
        raise InvalidBenchmarkIterationsError
    request = build_scenario_request()
    warmup = estimate_protein_rna_discordance_baseline(request)
    samples: list[int] = []
    deterministic = True
    for _ in range(iterations):
        started = perf_counter_ns()
        result = estimate_protein_rna_discordance_baseline(request)
        samples.append(perf_counter_ns() - started)
        deterministic = deterministic and result == warmup
    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id=M1003_MODULE_ID,
        contract_version=M1003_CONTRACT_VERSION,
        workload="three-target-locked-robust-linear-baseline",
        timed_boundary="estimate_protein_rna_discordance_baseline",
        iterations=iterations,
        warmup_count=WARMUP_COUNT,
        target_count=len(request.configuration.target_feature_ids),
        request_digest=warmup.request_digest,
        result_digest=warmup.result_digest,
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=M1003_MEAN_BUDGET_NS,
        p95_budget_ns=M1003_P95_BUDGET_NS,
        deterministic=deterministic,
        passed=deterministic and mean <= M1003_MEAN_BUDGET_NS and p95 <= M1003_P95_BUDGET_NS,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=ITERATIONS)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_benchmark(arguments.iterations)
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    return 0 if report.passed else 1


__all__ = ["BenchmarkReport", "InvalidBenchmarkIterationsError", "main", "run_benchmark"]


if __name__ == "__main__":
    raise SystemExit(main())
