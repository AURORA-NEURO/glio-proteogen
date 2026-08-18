"""Bounded benchmark for the M08-07 public service boundary."""

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

from evals.m08_07.run import build_request, candidate
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_07_calibration_selective_prediction as m0807,
)

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


class NonDeterministicBenchmarkError(RuntimeError):
    """The public operation returned different results for the same request."""


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    iterations: int
    workload: str
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    result_digest: str
    passed: bool


def run_benchmark() -> BenchmarkReport:
    service = m0807.M0807Service()
    request = build_request(candidate())
    warm = service.execute(request)
    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = perf_counter_ns()
        result = service.execute(request)
        samples.append(perf_counter_ns() - started)
        if result != warm:
            raise NonDeterministicBenchmarkError
    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M08-07",
        iterations=ITERATIONS,
        workload="quality_gated_calibrated_candidate_service_execution",
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        result_digest=warm.result_digest,
        passed=mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run_benchmark()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
