"""Benchmark the public M05-05 detector on a genuine M05-03-backed request."""

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

from evals.m05_05.run import build_scenario
from glio_proteogen.contracts.m05_05 import (
    M0505_BENCHMARK_ITERATIONS,
    M0505_BENCHMARK_WARMUPS,
    M0505_CONTRACT_VERSION,
    M0505_DETECTOR_CLASS_COUNT,
    M0505_MAX_CANONICAL_REQUEST_BYTES,
    M0505_MEAN_BUDGET_NS,
    M0505_MODULE_ID,
    M0505_P95_BUDGET_NS,
    PtmLocalizationArtifactDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    detect_ptm_localization_artifacts,
)


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    warmup_count: int
    detector_class_count: int
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
    """The public builder no longer supplies the frozen seven-class workload."""


class NonDeterministicBenchmarkError(RuntimeError):
    """A timed detector result disagreed with the untimed warmup."""


def run_benchmark() -> BenchmarkReport:
    """Build outside timing, warm once, then time exactly 25 public detections."""

    scenario = build_scenario("clear")
    warmup = detect_ptm_localization_artifacts(scenario.request)
    if (
        warmup.disposition is not PtmLocalizationArtifactDisposition.CLEARED
        or len(warmup.artifact_posteriors) != M0505_DETECTOR_CLASS_COUNT
        or warmup.contamination_flags
        or warmup.exclusion_mask
    ):
        raise InvalidRepresentativeWorkloadError

    samples: list[int] = []
    for _ in range(M0505_BENCHMARK_ITERATIONS):
        started = perf_counter_ns()
        result = detect_ptm_localization_artifacts(scenario.request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)

    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    request_bytes = len(canonical_json_bytes(scenario.request))
    return BenchmarkReport(
        module_id=M0505_MODULE_ID,
        contract_version=M0505_CONTRACT_VERSION,
        workload="genuine_m05_03_replay_one_target_seven_detector_classes",
        timed_boundary="detect_ptm_localization_artifacts_only",
        iterations=M0505_BENCHMARK_ITERATIONS,
        warmup_count=M0505_BENCHMARK_WARMUPS,
        detector_class_count=len(warmup.artifact_posteriors),
        request_bytes=request_bytes,
        result_bytes=len(canonical_json_bytes(warmup)),
        request_digest=warmup.request_digest,
        result_digest=warmup.result_digest,
        samples_ns=tuple(samples),
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=M0505_MEAN_BUDGET_NS,
        p95_budget_ns=M0505_P95_BUDGET_NS,
        passed=(
            request_bytes <= M0505_MAX_CANONICAL_REQUEST_BYTES
            and len(samples) == M0505_BENCHMARK_ITERATIONS
            and mean <= M0505_MEAN_BUDGET_NS
            and p95 <= M0505_P95_BUDGET_NS
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
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
