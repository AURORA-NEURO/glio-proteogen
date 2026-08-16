"""Benchmark exactly 25 public M05-02 calls on the maximum reconciled role shape."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from evals.m05_02.run import build_scenario_request
from glio_proteogen.contracts.m01_02 import EntityKind
from glio_proteogen.contracts.m05_02 import (
    M0502_ARTIFACT_ROLE_COUNT,
    M0502_DERIVATION_COUNT,
    M0502_MIN_DERIVATION_SOURCES,
    M0502_PHYSICAL_ENTITY_KIND_COUNT,
    PtmLocalizationLineageArtifactRole,
    PtmLocalizationLineageDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    reconcile_ptm_localization_identity_lineage,
)

DEFAULT_ITERATIONS = 25
MEAN_BUDGET_NS = 400_000_000
P95_BUDGET_NS = 750_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    iterations: int
    warmup_count: int
    physical_entity_kind_count: int
    artifact_role_count: int
    artifact_claim_count: int
    derivation_count: int
    derivation_source_count: int
    finding_count: int
    request_bytes: int
    result_bytes: int
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
    """Prepare and warm once before timing only the public reconciliation operation."""

    if iterations < 1:
        raise InvalidIterationCountError
    request = build_scenario_request("canonical_reconciled")
    warmup = reconcile_ptm_localization_identity_lineage(request)
    entity_kinds = {node.kind for node in request.identity_resolution.graph.nodes}
    artifact_roles = {claim.role for claim in request.artifact_claims}
    if (
        warmup.disposition is not PtmLocalizationLineageDisposition.RECONCILED
        or len(entity_kinds) != M0502_PHYSICAL_ENTITY_KIND_COUNT
        or entity_kinds != set(EntityKind)
        or len(artifact_roles) != M0502_ARTIFACT_ROLE_COUNT
        or artifact_roles != set(PtmLocalizationLineageArtifactRole)
        or len(request.artifact_claims) != M0502_ARTIFACT_ROLE_COUNT
        or len(request.derivations) != M0502_DERIVATION_COUNT
        or len(request.derivations[0].source_claim_ids) != M0502_MIN_DERIVATION_SOURCES
        or warmup.findings
    ):
        raise InvalidRepresentativeWorkloadError
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = reconcile_ptm_localization_identity_lineage(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M05-02",
        contract_version="1.0.0",
        workload="maximum_reconciled_five_role_identity_lineage_graph",
        timed_boundary="reconcile_ptm_localization_identity_lineage_only",
        iterations=iterations,
        warmup_count=1,
        physical_entity_kind_count=len(entity_kinds),
        artifact_role_count=len(artifact_roles),
        artifact_claim_count=len(request.artifact_claims),
        derivation_count=len(request.derivations),
        derivation_source_count=len(request.derivations[0].source_claim_ids),
        finding_count=len(warmup.findings),
        request_bytes=len(canonical_json_bytes(request)),
        result_bytes=len(canonical_json_bytes(warmup)),
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
