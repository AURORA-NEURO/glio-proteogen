"""Benchmark the genuine representative M04-02 reconciliation chain."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from evals.m04_02.run import build_scenario_request
from glio_proteogen.contracts.m04_02 import (
    M0402_LIMITATION_COUNT,
    M0402_MIN_EVIDENCE,
    ProteoformLineageDisposition,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    reconcile_proteoform_identity_lineage,
)

DEFAULT_ITERATIONS = 25
MEAN_BUDGET_NS = 400_000_000
P95_BUDGET_NS = 600_000_000
EXPECTED_PHYSICAL_NODES = 7
EXPECTED_ARTIFACT_CLAIMS = 5
EXPECTED_DERIVATIONS = 1


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    warmup_count: int
    physical_node_count: int
    artifact_claim_count: int
    derivation_count: int
    finding_count: int
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


class InvalidIterationCountError(ValueError):
    pass


class InvalidRepresentativeWorkloadError(RuntimeError):
    pass


class NonDeterministicBenchmarkError(RuntimeError):
    pass


def run_benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    """Build genuine upstream outputs before timing only the public M04-02 operation."""

    if iterations < 1:
        raise InvalidIterationCountError
    request = build_scenario_request()
    warmup = reconcile_proteoform_identity_lineage(request)
    if (
        warmup.disposition is not ProteoformLineageDisposition.RECONCILED
        or len(request.identity_resolution.graph.nodes) != EXPECTED_PHYSICAL_NODES
        or len(request.artifact_claims) != EXPECTED_ARTIFACT_CLAIMS
        or len(request.derivations) != EXPECTED_DERIVATIONS
        or len(warmup.findings) != 0
        or len(warmup.evidence) != M0402_MIN_EVIDENCE
        or len(warmup.limitations) != M0402_LIMITATION_COUNT
        or warmup.parent_target != "protein_rna_discordance"
    ):
        raise InvalidRepresentativeWorkloadError
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = reconcile_proteoform_identity_lineage(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M04-02",
        contract_version="1.0.0",
        workload="genuine_seven_kind_five_claim_single_four_role_assembly",
        timed_boundary="reconcile_proteoform_identity_lineage_only",
        iterations=iterations,
        warmup_count=1,
        physical_node_count=len(request.identity_resolution.graph.nodes),
        artifact_claim_count=len(request.artifact_claims),
        derivation_count=len(request.derivations),
        finding_count=len(warmup.findings),
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
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_benchmark(arguments.iterations)
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


__all__ = ["BenchmarkReport", "main", "run_benchmark"]


if __name__ == "__main__":
    raise SystemExit(main())
