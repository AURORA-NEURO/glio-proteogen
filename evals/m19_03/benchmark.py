"""Bounded benchmark for the public M19-03 fusion engine."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns
from typing import Final

from tests.contract.test_m19_03_adversarial import _request

from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_03_fusion_aggregation import (
    M1903Engine,
)

ITERATIONS: Final = 25
WARMUP_COUNT: Final = 1
MEAN_BUDGET_NS: Final = 500_000_000
P95_BUDGET_NS: Final = 750_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    warmup_count: int
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
    request = _request()
    engine = M1903Engine()
    warmup = engine.adapt(request)
    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = perf_counter_ns()
        result = engine.adapt(request)
        samples.append(perf_counter_ns() - started)
        if result != warmup:
            raise RuntimeError("M19-03 benchmark result was not deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M19-03",
        contract_version="0.1.0-provisional",
        workload="component_specific_reliability_weighted_fusion",
        timed_boundary="M1903Engine.adapt_only",
        iterations=ITERATIONS,
        warmup_count=WARMUP_COUNT,
        request_digest=warmup.request_digest,
        result_digest=warmup.result_digest,
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_benchmark()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
