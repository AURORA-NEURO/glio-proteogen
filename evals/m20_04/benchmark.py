"""Bounded benchmark for the M20-04 intended-use adapter."""

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

from tests.contract.test_m20_04_hardening import _request

from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_04_intended_use_adapter import (  # noqa: E501
    M2004Engine,
)

ITERATIONS: Final = 10
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
    engine = M2004Engine()
    warmup = engine.adapt(request)
    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = perf_counter_ns()
        result = engine.adapt(request)
        samples.append(perf_counter_ns() - started)
        if result != warmup:
            raise RuntimeError("M20-04 benchmark result was not deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        "GLIO-PROTEOGEN-M20-04",
        "0.1.0-provisional",
        "bounded_intended_use_policy_adaptation",
        "M2004Engine.adapt_only",
        ITERATIONS,
        WARMUP_COUNT,
        warmup.request_digest,
        warmup.result_digest,
        mean,
        median(samples),
        p95,
        max(samples),
        MEAN_BUDGET_NS,
        P95_BUDGET_NS,
        mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
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
