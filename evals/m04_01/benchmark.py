"""Benchmark only public M04-01 evaluation on one maximum conformant profile."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter_ns

from evals.m04_01.run import build_scenario_request
from glio_proteogen.contracts.m04_01 import (
    M0401_EVIDENCE_COUNT,
    M0401_LIMITATION_COUNT,
    M0401_MAX_APPROVED_REFERENCE_BUNDLES,
    M0401_MAX_APPROVED_VERSIONS,
    M0401_MAX_COORDINATE_PROFILES,
    M0401_MAX_EVIDENCE_CLASSES,
    M0401_MAX_ISOFORM_DISCRIMINATORS,
    M0401_MAX_LABILE_HANDLINGS,
    M0401_MAX_QUANTIFICATION_PAIRS,
    M0401_SECTION_COUNT,
    ProteoformApplicability,
    ProteoformProtocolConformanceDisposition,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    evaluate_proteoform_protocol,
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
    protocol_section_count: int
    applicability_count: int
    reference_bundle_count: int
    approved_version_count: int
    coordinate_profile_count: int
    quantification_pair_count: int
    evidence_class_count: int
    approved_labile_handling_count: int
    approved_isoform_discriminator_count: int
    minimum_isoform_discriminators: int
    evidence_count: int
    limitation_count: int
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


class InvalidMaximumWorkloadError(RuntimeError):
    pass


class NonDeterministicBenchmarkError(RuntimeError):
    pass


def run_benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    """Prepare the maximum strict request before timing only the public evaluator."""

    if iterations < 1:
        raise InvalidIterationCountError
    request = build_scenario_request("maximum_profile_shape_conforms")
    profile = request.conformance_profile
    warmup = evaluate_proteoform_protocol(request)
    if (
        warmup.disposition is not ProteoformProtocolConformanceDisposition.CONFORMANT
        or len(warmup.findings) != M0401_SECTION_COUNT
        or len(profile.approved_applicabilities) != len(ProteoformApplicability)
        or len(profile.approved_reference_bundles) != M0401_MAX_APPROVED_REFERENCE_BUNDLES
        or len(profile.approved_assay_protocol_versions) != M0401_MAX_APPROVED_VERSIONS
        or len(profile.approved_specimen_processing_versions) != M0401_MAX_APPROVED_VERSIONS
        or len(profile.approved_controlled_vocabularies) != M0401_MAX_APPROVED_VERSIONS
        or len(profile.approved_unit_system_versions) != M0401_MAX_APPROVED_VERSIONS
        or len(profile.approved_coordinate_profiles) != M0401_MAX_COORDINATE_PROFILES
        or len(profile.approved_quantification_pairs) != M0401_MAX_QUANTIFICATION_PAIRS
        or len(profile.approved_evidence_classes) != M0401_MAX_EVIDENCE_CLASSES
        or len(profile.approved_labile_modification_handlings) != M0401_MAX_LABILE_HANDLINGS
        or len(profile.approved_isoform_discriminators) != M0401_MAX_EVIDENCE_CLASSES
        or profile.minimum_isoform_discriminators != M0401_MAX_ISOFORM_DISCRIMINATORS
        or len(warmup.evidence) != M0401_EVIDENCE_COUNT
        or len(warmup.limitations) != M0401_LIMITATION_COUNT
        or warmup.parent_target != "protein_rna_discordance"
    ):
        raise InvalidMaximumWorkloadError
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = evaluate_proteoform_protocol(request)
        elapsed = perf_counter_ns() - started
        if result != warmup:
            raise NonDeterministicBenchmarkError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id="GLIO-PROTEOGEN-M04-01",
        contract_version="1.0.0",
        workload="maximum_conformant_proteoform_protocol_profile",
        timed_boundary="evaluate_proteoform_protocol_only",
        iterations=iterations,
        protocol_section_count=len(warmup.findings),
        applicability_count=len(profile.approved_applicabilities),
        reference_bundle_count=len(profile.approved_reference_bundles),
        approved_version_count=len(profile.approved_assay_protocol_versions),
        coordinate_profile_count=len(profile.approved_coordinate_profiles),
        quantification_pair_count=len(profile.approved_quantification_pairs),
        evidence_class_count=len(profile.approved_evidence_classes),
        approved_labile_handling_count=len(profile.approved_labile_modification_handlings),
        approved_isoform_discriminator_count=len(profile.approved_isoform_discriminators),
        minimum_isoform_discriminators=profile.minimum_isoform_discriminators,
        evidence_count=len(warmup.evidence),
        limitation_count=len(warmup.limitations),
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
