"""Small deterministic benchmark for the M05-08 public build boundary."""

# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from tests.modules.c05_ptm_localization.test_m05_08_release_packaging import (
    _valid_fixture,
    _Verifier,
)

from glio_proteogen.contracts.m05_08 import PtmLocalizationReleaseDisposition
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging import (
    M0508PtmLocalizationReleaseEngine,
)

DEFAULT_ITERATIONS = 10
MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    mean_ns: float
    median_ns: float
    p95_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    package_member_count: int
    passed: bool


def benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    request, artifacts = _valid_fixture()
    verifier = _Verifier()
    engine = M0508PtmLocalizationReleaseEngine(verifier)
    warmup = engine.build(request, artifacts)
    if warmup.result.disposition is not PtmLocalizationReleaseDisposition.RELEASED:
        raise RuntimeError("benchmark fixture did not release")
    samples: list[int] = []
    package_member_count = warmup.result.package_member_count
    for _ in range(iterations):
        verifier.calls.clear()
        started = perf_counter_ns()
        result = engine.build(request, artifacts)
        samples.append(perf_counter_ns() - started)
        if (
            result.result.disposition is not PtmLocalizationReleaseDisposition.RELEASED
            or result.package_bytes is None
            or len(verifier.calls) != 1
        ):
            raise RuntimeError("benchmark result was not deterministic")
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M05-08",
        contract_version="0.1.0-provisional",
        workload="single canonical parent variant-peptide handoff",
        timed_boundary="M0508PtmLocalizationReleaseEngine.build",
        iterations=iterations,
        mean_ns=mean,
        median_ns=median(samples),
        p95_ns=p95,
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        package_member_count=package_member_count,
        passed=mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = benchmark(args.iterations)
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["BenchmarkReport", "benchmark", "main"]
