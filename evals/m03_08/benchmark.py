"""Benchmark the public M03-08 build at the exact 64+64 metadata ceiling."""

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

from evals.m03_08.run import build_maximum_scenario
from glio_proteogen.contracts.m03_08 import (
    M0308_ARCHIVE_MEMBER_COUNT,
    M0308_MAX_REFERENCE_VERSIONS,
    M0308_MAX_SOFTWARE_VERSIONS,
    M0308_MODULE_ID,
    ProteinInferenceReleaseDisposition,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.engine import (
    build_protein_inference_release,
)

DEFAULT_ITERATIONS: Final = 25
WARMUP_COUNT: Final = 1
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


class _BenchmarkBuildError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    module_id: str
    contract_version: str
    workload: str
    timed_boundary: str
    warmup_count: int
    iterations: int
    software_version_count: int
    reference_version_count: int
    artifact_count: int
    stage_count: int
    archive_member_count: int
    mean_ns: float
    median_ns: float
    p95_ns: int
    minimum_ns: int
    maximum_ns: int
    mean_budget_ns: int
    p95_budget_ns: int
    passed: bool


def benchmark(iterations: int = DEFAULT_ITERATIONS) -> BenchmarkReport:
    """Time only the public build with all expensive upstream preparation excluded."""

    if iterations <= 0:
        raise ValueError(iterations)
    scenario = build_maximum_scenario()
    warmup = build_protein_inference_release(
        scenario.request,
        scenario.artifacts,
        scenario.stages,
        scenario.verifier,
    )
    if warmup.package_bytes is None:
        raise _BenchmarkBuildError
    samples: list[int] = []
    archive_member_count = 0
    for _ in range(iterations):
        scenario.verifier.calls.clear()
        started = perf_counter_ns()
        built = build_protein_inference_release(
            scenario.request,
            scenario.artifacts,
            scenario.stages,
            scenario.verifier,
        )
        samples.append(perf_counter_ns() - started)
        if (
            built.result.disposition is not ProteinInferenceReleaseDisposition.RELEASED
            or built.package_bytes is None
            or built.result.package_descriptor is None
            or len(scenario.verifier.calls) != 1
        ):
            raise _BenchmarkBuildError
        archive_member_count = built.result.package_descriptor.member_count
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)]
    mean = fmean(samples)
    return BenchmarkReport(
        module_id=M0308_MODULE_ID,
        contract_version="1.0.0",
        workload="public_build_exact_64_software_64_reference_shape",
        timed_boundary="build_protein_inference_release",
        warmup_count=WARMUP_COUNT,
        iterations=iterations,
        software_version_count=len(scenario.request.software_versions),
        reference_version_count=len(scenario.request.reference_versions),
        artifact_count=len(scenario.artifacts),
        stage_count=len(scenario.stages),
        archive_member_count=archive_member_count,
        mean_ns=mean,
        median_ns=median(samples),
        p95_ns=p95,
        minimum_ns=min(samples),
        maximum_ns=max(samples),
        mean_budget_ns=MEAN_BUDGET_NS,
        p95_budget_ns=P95_BUDGET_NS,
        passed=(
            len(scenario.request.software_versions) == M0308_MAX_SOFTWARE_VERSIONS
            and len(scenario.request.reference_versions) == M0308_MAX_REFERENCE_VERSIONS
            and archive_member_count == M0308_ARCHIVE_MEMBER_COUNT
            and mean <= MEAN_BUDGET_NS
            and p95 <= P95_BUDGET_NS
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = benchmark(args.iterations)
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
