"""Benchmark the public M05-06 harmonizer on a genuine M05-05 replay request."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.m05_06.run import build_scenario
from glio_proteogen.contracts.m05_06 import (
    M0506_BENCHMARK_ITERATIONS,
    M0506_BENCHMARK_WARMUPS,
    M0506_CONTRACT_VERSION,
    M0506_MAX_CANONICAL_REQUEST_BYTES,
    M0506_MAX_STAGES,
    M0506_MEAN_BUDGET_NS,
    M0506_MODULE_ID,
    M0506_P95_BUDGET_NS,
    PtmLocalizationHarmonizationDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    harmonize_ptm_localization_analysis,
)


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    warmup_count: int
    stage_count: int
    request_bytes: int
    result_bytes: int
    request_digest: str
    result_digest: str
    samples_ns: tuple[int, ...]
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


class InvalidRepresentativeWorkloadError(RuntimeError):
    """The public builder no longer supplies the frozen accepted workload."""


class NonDeterministicBenchmarkError(RuntimeError):
    """A timed harmonization result disagreed with its untimed warmup."""


def run_benchmark() -> BenchmarkReport:
    """Build outside timing, warm once, then time exactly 25 public calls."""

    scenario = build_scenario("clear")
    warmup = harmonize_ptm_localization_analysis(scenario.request)
    if (
        warmup.disposition is not PtmLocalizationHarmonizationDisposition.ACCEPTED
        or warmup.analysis is None
        or warmup.transformation_manifest is None
        or len(warmup.transformation_manifest.stages) != M0506_MAX_STAGES
    ):
        raise InvalidRepresentativeWorkloadError

    samples: list[int] = []
    for _ in range(M0506_BENCHMARK_ITERATIONS):
        started = perf_counter_ns()
        result = harmonize_ptm_localization_analysis(scenario.request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)

    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    request_bytes = len(canonical_json_bytes(scenario.request))
    return BenchmarkReport(
        module_id=M0506_MODULE_ID,
        contract_version=M0506_CONTRACT_VERSION,
        workload="genuine_m05_05_replay_one_target_eight_factor_harmonization",
        timed_boundary="harmonize_ptm_localization_analysis_only",
        iterations=M0506_BENCHMARK_ITERATIONS,
        warmup_count=M0506_BENCHMARK_WARMUPS,
        stage_count=len(warmup.transformation_manifest.stages),
        request_bytes=request_bytes,
        result_bytes=len(canonical_json_bytes(warmup)),
        request_digest=warmup.request_digest,
        result_digest=warmup.result_digest,
        samples_ns=tuple(samples),
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=M0506_MEAN_BUDGET_NS,
        p95_budget_ns=M0506_P95_BUDGET_NS,
        passed=(
            request_bytes <= M0506_MAX_CANONICAL_REQUEST_BYTES
            and len(samples) == M0506_BENCHMARK_ITERATIONS
            and mean <= M0506_MEAN_BUDGET_NS
            and p95 <= M0506_P95_BUDGET_NS
        ),
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


__all__ = ["BenchmarkReport", "main", "run_benchmark"]


if __name__ == "__main__":
    raise SystemExit(main())
