"""Benchmark exactly 25 public M05-01 calls on the maximum supported shape."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from evals.m05_01.run import build_scenario_request
from glio_proteogen.contracts.m05_01 import (
    M0501_MAX_APPROVED_REFERENCE_BUNDLES,
    M0501_MAX_APPROVED_VERSIONS,
    M0501_MAX_COMPATIBILITY_RULES,
    M0501_MAX_METADATA_FIELDS,
    M0501_MAX_UNIT_POLICIES,
    M0501_MAX_VOCABULARY_TERMS,
    PtmLocalizationProtocolConformanceDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata import (
    evaluate_ptm_localization_protocol,
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
    warmup_count: int
    reference_bundle_count: int
    approved_version_count: int
    vocabulary_count: int
    vocabulary_term_count: int
    unit_policy_count: int
    metadata_field_count: int
    compatibility_rule_count: int
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


class InvalidMaximumWorkloadError(RuntimeError):
    pass


class NonDeterministicBenchmarkError(RuntimeError):
    pass


def run_benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    """Prepare maximum input and warm-up before timing only the public operation."""

    if iterations < 1:
        raise InvalidIterationCountError
    request = build_scenario_request("maximum_profile_shape_conforms")
    protocol = request.protocol_schema
    profile = request.conformance_profile
    warmup = evaluate_ptm_localization_protocol(request)
    if (
        warmup.disposition is not PtmLocalizationProtocolConformanceDisposition.CONFORMANT
        or len(profile.approved_reference_bundles) != M0501_MAX_APPROVED_REFERENCE_BUNDLES
        or len(profile.approved_protocol_versions) != M0501_MAX_APPROVED_VERSIONS
        or len(profile.approved_vocabulary_versions) != M0501_MAX_APPROVED_VERSIONS
        or len(protocol.controlled_vocabularies) != M0501_MAX_APPROVED_VERSIONS
        or len(protocol.controlled_vocabularies[0].terms) != M0501_MAX_VOCABULARY_TERMS
        or len(protocol.unit_policies) != M0501_MAX_UNIT_POLICIES
        or len(protocol.metadata_fields) != M0501_MAX_METADATA_FIELDS
        or len(protocol.compatibility_rules) != M0501_MAX_COMPATIBILITY_RULES
    ):
        raise InvalidMaximumWorkloadError
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = evaluate_ptm_localization_protocol(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M05-01",
        contract_version="1.0.0",
        workload="maximum_conformant_ptm_localization_protocol_profile",
        timed_boundary="evaluate_ptm_localization_protocol_only",
        iterations=iterations,
        warmup_count=1,
        reference_bundle_count=len(profile.approved_reference_bundles),
        approved_version_count=len(profile.approved_protocol_versions),
        vocabulary_count=len(protocol.controlled_vocabularies),
        vocabulary_term_count=len(protocol.controlled_vocabularies[0].terms),
        unit_policy_count=len(protocol.unit_policies),
        metadata_field_count=len(protocol.metadata_fields),
        compatibility_rule_count=len(protocol.compatibility_rules),
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
