"""Benchmark the public M06-03 baseline estimator at its frozen workload shape."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m06_03.run import build_scenario
from glio_proteogen.contracts.m06_03 import (
    M0603_BENCHMARK_ITERATIONS,
    M0603_BENCHMARK_WARMUPS,
    M0603_CONTRACT_VERSION,
    M0603_MEAN_BUDGET_NS,
    M0603_MODULE_ID,
    M0603_P95_BUDGET_NS,
    BaselineResultStatus,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator import (
    estimate_protein_abundance_baseline,
)

FEATURE_COUNT: Final = 3


class InvalidRepresentativeWorkloadError(RuntimeError):
    """The evaluator fixture no longer supplies the frozen benchmark shape."""


class NonDeterministicBenchmarkError(RuntimeError):
    """A timed public call disagreed with its untimed warm-up result."""


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    warmup_count: int
    feature_count: int
    estimate_count: int
    diagnostic_count: int
    request_digest: str
    result_digest: str
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


def run_benchmark() -> BenchmarkReport:
    """Warm once, then time exactly the locked 25 public computations."""

    request = build_scenario("clear").request
    warmup = estimate_protein_abundance_baseline(request)
    if (
        warmup.status is not BaselineResultStatus.ESTIMATED
        or len(request.feature_values) != FEATURE_COUNT
        or len(warmup.estimates) != FEATURE_COUNT
        or len(warmup.diagnostics) != FEATURE_COUNT
    ):
        raise InvalidRepresentativeWorkloadError

    samples: list[int] = []
    for _ in range(M0603_BENCHMARK_ITERATIONS):
        started = perf_counter_ns()
        result = estimate_protein_abundance_baseline(request)
        samples.append(perf_counter_ns() - started)
        if result != warmup:
            raise NonDeterministicBenchmarkError

    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id=M0603_MODULE_ID,
        contract_version=M0603_CONTRACT_VERSION,
        workload="genuine_clear_formal_state_three_feature_shape",
        timed_boundary="estimate_protein_abundance_baseline_only",
        iterations=M0603_BENCHMARK_ITERATIONS,
        warmup_count=M0603_BENCHMARK_WARMUPS,
        feature_count=len(request.feature_values),
        estimate_count=len(warmup.estimates),
        diagnostic_count=len(warmup.diagnostics),
        request_digest=warmup.request_digest,
        result_digest=warmup.result_digest,
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=M0603_MEAN_BUDGET_NS,
        p95_budget_ns=M0603_P95_BUDGET_NS,
        passed=mean <= M0603_MEAN_BUDGET_NS and p95 <= M0603_P95_BUDGET_NS,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_benchmark()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BenchmarkReport",
    "InvalidRepresentativeWorkloadError",
    "NonDeterministicBenchmarkError",
    "main",
    "run_benchmark",
]
