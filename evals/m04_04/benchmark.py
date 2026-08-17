"""Benchmark only public M04-04 computation at the maximum supported metadata shape."""

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

from evals.m04_04.run import build_representative_quality_fixture
from glio_proteogen.contracts.m04_04 import (
    M0404_COMPUTED_METRIC_COUNT,
    M0404_LIMITATION_COUNT,
    M0404_MAX_EVIDENCE,
    M0404_MAX_PROFILES,
    M0404_METRIC_COUNT,
    M0404_MODULE_ID,
    M0404_ROLE_COUNT,
    ProteoformQualityDisposition,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    compute_proteoform_quality_metrics,
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
    role_count: int
    profile_count: int
    threshold_count: int
    fact_count: int
    metric_count: int
    evidence_count: int
    limitation_count: int
    request_digest: str
    result_digest: str
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


class InvalidRepresentativeWorkloadError(RuntimeError):
    """The public builder no longer supplies the frozen maximum supported shape."""


class NonDeterministicBenchmarkError(RuntimeError):
    """A timed computation disagreed with the untimed warm-up result."""


def run_benchmark() -> BenchmarkReport:
    """Build and warm outside timing, then time exactly 25 public computations."""

    scenario = build_representative_quality_fixture()
    request = scenario.request
    warmup = compute_proteoform_quality_metrics(request)
    ledger = request.fact_ledger
    metric_count = sum(len(item.metrics) for item in warmup.assay_quality)
    threshold_count = sum(len(item.thresholds) for item in request.policy.profiles)
    if (
        ledger is None
        or len(request.policy.profiles) != M0404_MAX_PROFILES
        or threshold_count != M0404_MAX_PROFILES * M0404_METRIC_COUNT
        or len(ledger.role_facts) != M0404_ROLE_COUNT
        or warmup.disposition is not ProteoformQualityDisposition.QUALIFIED
        or len(warmup.assay_quality) != M0404_ROLE_COUNT
        or metric_count != M0404_COMPUTED_METRIC_COUNT
        or len(warmup.evidence) != M0404_MAX_EVIDENCE
        or len(warmup.limitations) != M0404_LIMITATION_COUNT
        or warmup.parent_target != "protein_rna_discordance"
    ):
        raise InvalidRepresentativeWorkloadError

    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = perf_counter_ns()
        result = compute_proteoform_quality_metrics(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)

    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id=M0404_MODULE_ID,
        contract_version="1.0.0",
        workload="genuine_maximum_supported_quality_metadata_shape",
        timed_boundary="compute_proteoform_quality_metrics_only",
        iterations=ITERATIONS,
        warmup_count=WARMUP_COUNT,
        role_count=M0404_ROLE_COUNT,
        profile_count=len(request.policy.profiles),
        threshold_count=threshold_count,
        fact_count=len(ledger.role_facts),
        metric_count=metric_count,
        evidence_count=len(warmup.evidence),
        limitation_count=len(warmup.limitations),
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
