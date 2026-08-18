"""Benchmark the genuine representative M03-02 reconciliation chain."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m03_02.run import build_scenario_request
from glio_proteogen.contracts.m03_02 import ReconciliationDisposition
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    reconcile_protein_inference_identity_lineage,
)

DEFAULT_ITERATIONS = 100
# Each measured operation strictly revalidates both embedded upstream result envelopes.
MEAN_BUDGET_NS = 400_000_000
P95_BUDGET_NS = 600_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    workload: str
    iterations: int
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


class InvalidIterationCountError(ValueError):
    def __init__(self) -> None:
        super().__init__("iterations must be positive")


class InvalidCanonicalWorkloadError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("canonical M03-02 workload did not reconcile")


class NonDeterministicBenchmarkError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("benchmark reconciliation was not deterministic")


def run_benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    """Measure the public operation with genuine upstream results built outside timing."""

    if iterations < 1:
        raise InvalidIterationCountError
    request = build_scenario_request()
    warmup = reconcile_protein_inference_identity_lineage(request)
    if warmup.disposition is not ReconciliationDisposition.RECONCILED:
        raise InvalidCanonicalWorkloadError
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = reconcile_protein_inference_identity_lineage(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        workload="genuine_m0102_to_m0301_to_m0302_canonical_chain",
        iterations=iterations,
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_benchmark(args.iterations)
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
