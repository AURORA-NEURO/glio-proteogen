"""Benchmark only public M03-05 detection on one fully prepared genuine chain."""

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

from evals.m03_05.run import build_scenario
from glio_proteogen.contracts.m03_05 import (
    M0305_SIGNAL_COUNT,
    ProteinInferenceArtifactDisposition,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    detect_protein_inference_artifacts,
)

DEFAULT_ITERATIONS = 25
MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    unit_count: int
    signal_score_count: int
    request_digest: str
    result_digest: str
    warmup_count: int
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
    """Prepare M01-02 through M03-04 and the ledger before timing only M03-05."""

    if iterations < 1:
        raise InvalidIterationCountError
    request = build_scenario().request
    ledger = request.evidence_ledger
    warmup = detect_protein_inference_artifacts(request)
    if (
        ledger is None
        or warmup.disposition is not ProteinInferenceArtifactDisposition.CLEARED
        or len(warmup.signal_scores) != len(ledger.units) * M0305_SIGNAL_COUNT
    ):
        raise InvalidCanonicalWorkloadError
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = detect_protein_inference_artifacts(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M03-05",
        contract_version="1.0.0",
        workload="genuine_m0102_through_m0304_prepared_m0305_artifact_evidence",
        timed_boundary="detect_protein_inference_artifacts_only",
        iterations=iterations,
        unit_count=len(ledger.units),
        signal_score_count=len(warmup.signal_scores),
        request_digest=warmup.request_digest,
        result_digest=warmup.result_digest,
        warmup_count=1,
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
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
