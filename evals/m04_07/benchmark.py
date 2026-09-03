"""Benchmark only public M04-07 routing on one prepared genuine chain."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import process_time_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m04_07.run import build_scenario
from glio_proteogen.contracts.m04_07 import ProteoformSupportDisposition
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    route_proteoform_support,
)

DEFAULT_ITERATIONS = 25
# Keep the tail ceiling fixed while reserving twenty percent between the
# steady-state mean and p95 ceilings.  This remains a two-gate benchmark: a
# sustained slowdown still fails the mean gate and a tail slowdown fails p95.
MEAN_BUDGET_NS = 2_500_000_000
P95_BUDGET_NS = 3_000_000_000
EXPECTED_ENVELOPE_COUNT = 1
EXPECTED_DIMENSION_COUNT = 8
MEASUREMENT_CLOCK = "process_time_ns"


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    measurement_clock: str
    iterations: int
    envelope_count: int
    dimension_count: int
    evidence_count: int
    request_digest: str
    result_digest: str
    warmup_count: int
    pre_timing_gc_collected_objects: int
    cyclic_gc_enabled_during_timing: bool
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
    """Prepare genuine M04-04/M04-06 results before timing only M04-07."""

    if iterations < 1:
        raise InvalidIterationCountError
    request = build_scenario().request
    warmup = route_proteoform_support(request)
    dimension_count = sum(len(assessment.dimensions) for assessment in warmup.envelope_assessments)
    if (
        warmup.disposition is not ProteoformSupportDisposition.SUPPORTED
        or len(warmup.envelope_assessments) != EXPECTED_ENVELOPE_COUNT
        or dimension_count != EXPECTED_DIMENSION_COUNT
        or len(warmup.matched_envelope_ids) != EXPECTED_ENVELOPE_COUNT
        or warmup.abstention_reasons
    ):
        raise InvalidCanonicalWorkloadError
    # Settle full-generation scan debt created by genuine upstream setup and
    # warm-up.  Cyclic GC stays enabled, so measured calls retain any
    # computation-owned collection cost.
    pre_timing_gc_collected_objects = gc.collect()
    samples: list[int] = []
    for _ in range(iterations):
        started = process_time_ns()
        result = route_proteoform_support(request)
        elapsed = process_time_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M04-07",
        contract_version="1.0.0",
        workload="genuine_m0404_and_m0406_prepared_joint_support_envelope",
        timed_boundary="route_proteoform_support_only",
        measurement_clock=MEASUREMENT_CLOCK,
        iterations=iterations,
        envelope_count=len(warmup.envelope_assessments),
        dimension_count=dimension_count,
        evidence_count=len(warmup.evidence),
        request_digest=warmup.request_digest,
        result_digest=warmup.result_digest,
        warmup_count=1,
        pre_timing_gc_collected_objects=pre_timing_gc_collected_objects,
        cyclic_gc_enabled_during_timing=gc.isenabled(),
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=gc.isenabled() and mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
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
