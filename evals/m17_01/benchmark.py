"""Bounded benchmark for the public M17-01 resolver operation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns
from typing import Final

from tests.runtime.test_m17_01_resolver import _candidate, _request

from glio_proteogen.contracts.m17_01 import M1701_MODULE_ID, CompatibilityStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_01_upstream_contract_resolver as m1701,
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
    candidate_count: int
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
    request = _request(
        _candidate("candidate.accepted", compatibility=CompatibilityStatus.COMPATIBLE),
        _candidate("candidate.rejected", compatibility=CompatibilityStatus.INCOMPATIBLE),
        _candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),
    )
    engine = m1701.M1701Engine()
    warmup = engine.resolve(request)
    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = perf_counter_ns()
        result = engine.resolve(request)
        samples.append(perf_counter_ns() - started)
        if result != warmup:
            raise RuntimeError("M17-01 benchmark result was not deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id=M1701_MODULE_ID,
        contract_version="0.1.0-provisional",
        workload="mixed_compatible_rejected_unknown_upstream_candidates",
        timed_boundary="M1701Engine.resolve_only",
        iterations=ITERATIONS,
        warmup_count=WARMUP_COUNT,
        candidate_count=len(request.candidates),
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
