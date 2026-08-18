"""Benchmark the deterministic M12-07 public operation."""

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

from evals.m12_07.run import build_scenario_request
from glio_proteogen.modules.c12_driver_protein_consequence.m12_07_plausibility_adjudicator import (
    M1207PlausibilityAdjudicatorEngine,
)

DEFAULT_ITERATIONS = 10
MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


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


def run_benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = build_scenario_request()
    engine = M1207PlausibilityAdjudicatorEngine()
    warmup = engine.adjudicate(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.adjudicate(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise RuntimeError(  # noqa: TRY003
                "M12-07 benchmark operation was not deterministic"
            )
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        workload="deterministic_m1207_six_control_adjudication",
        iterations=iterations,
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = asdict(run_benchmark(args.iterations))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
