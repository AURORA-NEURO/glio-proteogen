"""Benchmark only public M04-05 detection over one prepared genuine M04-04 chain."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from evals.m04_05.run import build_maximum_scenario_request
from glio_proteogen.contracts.m04_05 import (
    M0405_CONTRACT_VERSION,
    M0405_MAX_EVENTS,
    M0405_MAX_TARGETS,
    M0405_MODULE_ID,
    ProteoformArtifactDisposition,
    ProteoformArtifactEvidenceLedger,
    canonical_request_digest,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection import (
    detect_proteoform_artifacts,
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
    target_count: int
    event_count: int
    posterior_count: int
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
    """Prepare the genuine upstream chain before timing only M04-05."""

    if iterations < 1:
        raise InvalidIterationCountError
    request = build_maximum_scenario_request()
    ledger = request.evidence_ledger
    warmup = detect_proteoform_artifacts(request)
    if type(ledger) is not ProteoformArtifactEvidenceLedger:
        raise InvalidCanonicalWorkloadError
    target_count = len({item.target_id for item in ledger.events})
    if (
        target_count != M0405_MAX_TARGETS
        or warmup.disposition is not ProteoformArtifactDisposition.CLEARED
        or len(ledger.events) != M0405_MAX_EVENTS
        or len(warmup.artifact_posteriors) != M0405_MAX_EVENTS
    ):
        raise InvalidCanonicalWorkloadError
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = detect_proteoform_artifacts(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95_index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    mean = fmean(samples)
    p95 = ordered[p95_index]
    return BenchmarkReport(
        module_id=M0405_MODULE_ID,
        contract_version=M0405_CONTRACT_VERSION,
        workload="genuine M04-04 result plus the exact installed maximum aggregate ledger",
        timed_boundary="detect_proteoform_artifacts only",
        iterations=iterations,
        target_count=target_count,
        event_count=len(ledger.events),
        posterior_count=len(warmup.artifact_posteriors),
        request_digest=canonical_request_digest(request),
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
    arguments = _parser().parse_args(argv)
    report = run_benchmark(arguments.iterations)
    serialized = json.dumps(asdict(report), ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(serialized)
    else:
        arguments.output.write_text(serialized, encoding="utf-8", newline="\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_ITERATIONS",
    "MEAN_BUDGET_NS",
    "P95_BUDGET_NS",
    "BenchmarkReport",
    "main",
    "run_benchmark",
]
