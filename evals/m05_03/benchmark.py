"""Benchmark only public M05-03 ingestion on four genuine canonical manifests."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns
from typing import Final

from evals.m05_03.run import build_scenario
from glio_proteogen.contracts.m05_03 import (
    M0503_LIMITATION_COUNT,
    M0503_MAX_CANONICAL_REQUEST_BYTES,
    M0503_MIN_RECONCILED_EVIDENCE,
    M0503_MODULE_ID,
    M0503_ROLE_COUNT,
    PtmLocalizationRawInputDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion import (
    ingest_ptm_localization_raw_inputs,
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
    input_artifact_count: int
    document_count: int
    validated_input_count: int
    diagnostic_count: int
    evidence_count: int
    limitation_count: int
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
    """The public builder no longer supplies the frozen modest workload."""


class NonDeterministicBenchmarkError(RuntimeError):
    """A timed ingestion disagreed with the untimed warmup result."""


def run_benchmark() -> BenchmarkReport:
    """Build and warm outside timing, then time exactly 25 public ingestions."""

    scenario = build_scenario()
    warmup = ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)
    if (
        len(scenario.request.artifacts) != M0503_ROLE_COUNT
        or len(scenario.artifacts_by_role) != M0503_ROLE_COUNT
        or warmup.disposition is not PtmLocalizationRawInputDisposition.VALIDATED
        or len(warmup.validated_inputs) != M0503_ROLE_COUNT
        or len(warmup.diagnostics) != 0
        or len(warmup.evidence) != M0503_MIN_RECONCILED_EVIDENCE
        or len(warmup.limitations) != M0503_LIMITATION_COUNT
        or warmup.parent_target != "variant_peptide"
    ):
        raise InvalidRepresentativeWorkloadError

    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = perf_counter_ns()
        result = ingest_ptm_localization_raw_inputs(
            scenario.request,
            scenario.artifacts_by_role,
        )
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)

    ordered = sorted(samples)
    p95 = ordered[(95 * len(ordered) - 1) // 100]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id=M0503_MODULE_ID,
        contract_version="1.0.0",
        workload="genuine_four_modest_canonical_raw_manifest_documents",
        timed_boundary="ingest_ptm_localization_raw_inputs_only",
        iterations=ITERATIONS,
        warmup_count=WARMUP_COUNT,
        input_artifact_count=len(scenario.request.artifacts),
        document_count=len(scenario.artifacts_by_role),
        validated_input_count=len(warmup.validated_inputs),
        diagnostic_count=len(warmup.diagnostics),
        evidence_count=len(warmup.evidence),
        limitation_count=len(warmup.limitations),
        request_bytes=len(canonical_json_bytes(scenario.request)),
        result_bytes=len(canonical_json_bytes(warmup)),
        request_digest=warmup.request_digest,
        result_digest=warmup.result_digest,
        samples_ns=tuple(samples),
        mean_ns=mean,
        p50_ns=median(samples),
        p95_ns=p95,
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=(
            len(canonical_json_bytes(scenario.request)) <= M0503_MAX_CANONICAL_REQUEST_BYTES
            and mean <= MEAN_BUDGET_NS
            and p95 <= P95_BUDGET_NS
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
