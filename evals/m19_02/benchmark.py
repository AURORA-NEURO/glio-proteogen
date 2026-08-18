"""Bounded benchmark for the public M19-02 alignment operation."""

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

from tests.contract.test_m19_02_deep import _request

from glio_proteogen.contracts.m19_02 import M1902_MODULE_ID
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_02_cross_source_alignment as m1902,
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
    observation_count: int
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
    engine = m1902.M1902Engine()
    warmup = engine.align(request)
    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = perf_counter_ns()
        result = engine.align(request)
        samples.append(perf_counter_ns() - started)
        if result != warmup:
            raise RuntimeError("M19-02 benchmark result was not deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id=M1902_MODULE_ID,
        contract_version="0.1.0-provisional",
        workload="seven_dimension_supported_cross_source_alignment",
        timed_boundary="M1902Engine.align_only",
        iterations=ITERATIONS,
        warmup_count=WARMUP_COUNT,
        observation_count=len(request.observations),
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
