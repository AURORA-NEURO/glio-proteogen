"""Benchmark only the public M03-03 operation on a genuine prepared chain."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from evals.m03_03.run import build_scenario
from glio_proteogen.contracts.m03_03 import ProteinInferenceAdmissionDisposition
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    ingest_protein_inference_raw_inputs,
)

DEFAULT_ITERATIONS = 100
MEAN_BUDGET_NS = 150_000_000
P95_BUDGET_NS = 250_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    workload: str
    timed_boundary: str
    iterations: int
    source_count: int
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


class InvalidIterationCountError(ValueError):
    pass


class InvalidCanonicalWorkloadError(RuntimeError):
    pass


class NonDeterministicBenchmarkError(RuntimeError):
    pass


def run_benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    """Build M01-02→M03-01→M03-02 outside timing, then measure public M03-03."""

    if iterations < 1:
        raise InvalidIterationCountError
    scenario = build_scenario()
    warmup = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    if warmup.disposition is not ProteinInferenceAdmissionDisposition.VALIDATED:
        raise InvalidCanonicalWorkloadError
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        workload="genuine_m0102_m0301_m0302_prepared_m0303_admission",
        timed_boundary="ingest_protein_inference_raw_inputs_only",
        iterations=iterations,
        source_count=len(scenario.request.sources),
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
