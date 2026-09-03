"""Fresh-process performance gate for the synthetic GBM proteotype demo."""

# ruff: noqa: TC003, TRY003

from __future__ import annotations

import argparse
import math
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Final, Literal, Self

import numpy as np
from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, Sha256Digest
from glio_proteogen.research.gbm_functional_proteotype import (
    AXIS_ORDER,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    FunctionalProteotypeRequest,
    FunctionalProteotypeResult,
    ProteinEvidence,
    ProteinEvidenceState,
    algorithm_profile,
    analyze_functional_proteotype,
    functional_proteotype_catalog,
    synthetic_demo_request,
)
from glio_proteogen.research.gbm_functional_proteotype.canonical import (
    canonical_json_bytes,
    sha256_digest,
)

EVIDENCE_SCHEMA_VERSION: Final = "gbm-functional-proteotype-performance/1.0.0"
EXECUTION_ISOLATION: Final = "fresh-process"
DEMO_SCENARIO: Final = "synthetic-demo"
DEMO_OBSERVATION_COUNT: Final = 108
DEMO_BOOTSTRAP_REPLICATES: Final = 64
DEMO_PERMUTATION_REPLICATES: Final = 256
DEMO_P95_THRESHOLD_SECONDS: Final = 2.0
MAXIMUM_RESAMPLING_EVIDENCE_SCHEMA_VERSION: Final = (
    "gbm-functional-proteotype-maximum-resampling-performance/1.0.0"
)
MAXIMUM_RESAMPLING_SCENARIO: Final = "all-catalog-maximum-resampling"
MAXIMUM_RESAMPLING_PROFILE: Final = "maximum-resampling"
MAXIMUM_OBSERVATION_COUNT: Final = 600
MAXIMUM_BOOTSTRAP_REPLICATES: Final = 256
MAXIMUM_PERMUTATION_REPLICATES: Final = 2048
MAXIMUM_AXIS_OUTPUT_COUNT: Final = 4
MAXIMUM_ABLATION_OUTPUT_COUNT: Final = 52
MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS: Final = 10.0
MAXIMUM_REQUEST_DIGEST: Final = (
    "sha256:4c71578e2991e56ac0ffcd44c39f07a8b4661846f07a717084e3f2c258e55089"
)
MAXIMUM_REQUEST_BYTES: Final = 153_523
MAXIMUM_DEFAULT_WARMUP_RUNS: Final = 0
MAXIMUM_DEFAULT_MEASURED_RUNS: Final = 2
_MAXIMUM_COORDINATES: Final = (1.5, 0.5, -0.5, -1.5)
_MAXIMUM_PROVENANCE_DIGEST: Final = sha256_digest(
    {"benchmark": "gbm-functional-proteotype-maximum-v1"}
)
DEFAULT_WARMUP_RUNS: Final = 1
DEFAULT_MEASURED_RUNS: Final = 5
MAXIMUM_RUNS: Final = 32
P95_PERCENT: Final = 95
PERCENT_DENOMINATOR: Final = 100
ROUND_DIGITS_SECONDS: Final = 6
FRESH_PROCESS_TIMEOUT_SECONDS: Final = 90.0
FRESH_PROCESS_STARTUP_ALLOWANCE_SECONDS: Final = 30.0
_COVERAGE_ENVIRONMENT_VARIABLES: Final = (
    "COVERAGE_PROCESS_START",
    "COV_CORE_SOURCE",
    "COV_CORE_CONFIG",
    "COV_CORE_DATAFILE",
    "COV_CORE_BRANCH",
)


class BenchmarkError(RuntimeError):
    """Raised when the benchmark cannot produce trustworthy evidence."""


class DemoPerformanceEvidence(FrozenModel):
    """Machine-checkable receipt for the complete synthetic-demo workload."""

    schema_version: Literal["gbm-functional-proteotype-performance/1.0.0"] = EVIDENCE_SCHEMA_VERSION
    scenario: Literal["synthetic-demo"] = DEMO_SCENARIO
    execution_isolation: Literal["fresh-process"] = EXECUTION_ISOLATION
    fixture_digest: Sha256Digest
    profile_digest: Sha256Digest
    result_digest: Sha256Digest
    numpy_version: Literal["2.5.2"] = "2.5.2"
    python_version: NonEmptyStr
    platform: NonEmptyStr
    observation_count: Literal[108] = DEMO_OBSERVATION_COUNT
    bootstrap_replicates: Literal[64] = DEMO_BOOTSTRAP_REPLICATES
    permutation_replicates: Literal[256] = DEMO_PERMUTATION_REPLICATES
    request_bytes: int = Field(gt=0, le=MAX_REQUEST_BYTES)
    result_bytes: int = Field(gt=0, le=MAX_RESULT_BYTES)
    warmup_runs: int = Field(ge=0, le=MAXIMUM_RUNS)
    measured_runs: int = Field(ge=1, le=MAXIMUM_RUNS)
    durations_seconds: tuple[float, ...] = Field(min_length=1, max_length=MAXIMUM_RUNS)
    p95_seconds: float = Field(ge=0.0)
    p95_threshold_seconds: float = Field(default=DEMO_P95_THRESHOLD_SECONDS, gt=0.0)
    deterministic: Literal[True] = True
    passed: bool

    @model_validator(mode="after")
    def evidence_is_internally_consistent(self) -> Self:
        if not math.isclose(
            self.p95_threshold_seconds,
            DEMO_P95_THRESHOLD_SECONDS,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise ValueError("the synthetic-demo p95 threshold must remain exactly two seconds")
        if len(self.durations_seconds) != self.measured_runs:
            raise ValueError("measured run count must equal the duration count")
        if not all(math.isfinite(item) and item >= 0.0 for item in self.durations_seconds):
            raise ValueError("durations must be finite and non-negative")
        expected_p95 = nearest_rank_percentile(self.durations_seconds, P95_PERCENT)
        if not math.isclose(
            self.p95_seconds,
            expected_p95,
            rel_tol=0.0,
            abs_tol=10**-ROUND_DIGITS_SECONDS,
        ):
            raise ValueError("reported p95 does not match the measured durations")
        if self.passed is not (self.p95_seconds < self.p95_threshold_seconds):
            raise ValueError("pass state must be derived from the strict p95 threshold")
        return self


class MaximumResamplingPerformanceEvidence(FrozenModel):
    """Receipt for all 600 catalog proteins at both resampling maxima."""

    schema_version: Literal["gbm-functional-proteotype-maximum-resampling-performance/1.0.0"] = (
        MAXIMUM_RESAMPLING_EVIDENCE_SCHEMA_VERSION
    )
    scenario: Literal["all-catalog-maximum-resampling"] = MAXIMUM_RESAMPLING_SCENARIO
    resampling_profile: Literal["maximum-resampling"] = MAXIMUM_RESAMPLING_PROFILE
    execution_isolation: Literal["fresh-process"] = EXECUTION_ISOLATION
    fixture_digest: Sha256Digest
    profile_digest: Sha256Digest
    result_digest: Sha256Digest
    numpy_version: Literal["2.5.2"] = "2.5.2"
    python_version: NonEmptyStr
    platform: NonEmptyStr
    observation_count: Literal[600] = MAXIMUM_OBSERVATION_COUNT
    active_catalog_protein_count: Literal[600] = MAXIMUM_OBSERVATION_COUNT
    bootstrap_replicates: Literal[256] = MAXIMUM_BOOTSTRAP_REPLICATES
    permutation_replicates: Literal[2048] = MAXIMUM_PERMUTATION_REPLICATES
    bootstrap_replicates_used: Literal[256] = MAXIMUM_BOOTSTRAP_REPLICATES
    permutation_replicates_used: Literal[2048] = MAXIMUM_PERMUTATION_REPLICATES
    solver_converged: Literal[True] = True
    axis_output_count: Literal[4] = MAXIMUM_AXIS_OUTPUT_COUNT
    supported_axis_output_count: Literal[4] = MAXIMUM_AXIS_OUTPUT_COUNT
    ablation_output_count: Literal[52] = MAXIMUM_ABLATION_OUTPUT_COUNT
    request_bytes: int = Field(gt=0, le=MAX_REQUEST_BYTES)
    result_bytes: int = Field(gt=0, le=MAX_RESULT_BYTES)
    warmup_runs: int = Field(ge=0, le=MAXIMUM_RUNS)
    measured_runs: int = Field(ge=1, le=MAXIMUM_RUNS)
    durations_seconds: tuple[float, ...] = Field(min_length=1, max_length=MAXIMUM_RUNS)
    p95_seconds: float = Field(ge=0.0)
    p95_threshold_seconds: float = Field(
        default=MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS,
        gt=0.0,
    )
    deterministic: Literal[True] = True
    passed: bool

    @model_validator(mode="after")
    def evidence_is_internally_consistent(self) -> Self:
        if self.fixture_digest != MAXIMUM_REQUEST_DIGEST:
            raise ValueError("the maximum-resampling fixture digest is not locked")
        if self.request_bytes != MAXIMUM_REQUEST_BYTES:
            raise ValueError("the maximum-resampling request size is not locked")
        if not math.isclose(
            self.p95_threshold_seconds,
            MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise ValueError("the maximum-resampling p95 threshold must remain exactly ten seconds")
        if len(self.durations_seconds) != self.measured_runs:
            raise ValueError("measured run count must equal the duration count")
        if not all(math.isfinite(item) and item >= 0.0 for item in self.durations_seconds):
            raise ValueError("durations must be finite and non-negative")
        expected_p95 = nearest_rank_percentile(self.durations_seconds, P95_PERCENT)
        if not math.isclose(
            self.p95_seconds,
            expected_p95,
            rel_tol=0.0,
            abs_tol=10**-ROUND_DIGITS_SECONDS,
        ):
            raise ValueError("reported p95 does not match the measured durations")
        if self.passed is not (self.p95_seconds < self.p95_threshold_seconds):
            raise ValueError("pass state must be derived from the strict p95 threshold")
        return self


def nearest_rank_percentile(values: Sequence[float], percentile: int) -> float:
    """Return a deterministic nearest-rank percentile."""

    if not values:
        raise ValueError("percentile requires at least one value")
    if not 1 <= percentile <= PERCENT_DENOMINATOR:
        raise ValueError("percentile must be in [1, 100]")
    ordered = sorted(values)
    rank = math.ceil(percentile * len(ordered) / PERCENT_DENOMINATOR)
    return float(ordered[rank - 1])


def _validate_run_counts(*, warmup_runs: int, measured_runs: int) -> None:
    if not 0 <= warmup_runs <= MAXIMUM_RUNS:
        raise ValueError("warmup runs must be between zero and 32")
    if not 1 <= measured_runs <= MAXIMUM_RUNS:
        raise ValueError("measured runs must be between one and 32")


@lru_cache(maxsize=1)
def maximum_resampling_request() -> FunctionalProteotypeRequest:
    """Build the exact all-catalog, maximum-resampling benchmark request."""

    catalog = functional_proteotype_catalog()
    observations = tuple(
        ProteinEvidence(
            observation_id=f"maximum.{axis.value}.{row.source_rank:03d}",
            gene_symbol=row.gene_symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=_MAXIMUM_COORDINATES[axis_index] * row.source_loading,
            standard_error=0.30,
            quality_weight=0.90,
            provenance_digest=_MAXIMUM_PROVENANCE_DIGEST,
        )
        for axis_index, axis in enumerate(AXIS_ORDER)
        for row in catalog.axes[axis.value]
    )
    request = FunctionalProteotypeRequest(
        sample_id="gbm-functional-proteotype-maximum-v1",
        observations=observations,
        bootstrap_replicates=MAXIMUM_BOOTSTRAP_REPLICATES,
        permutation_replicates=MAXIMUM_PERMUTATION_REPLICATES,
        effect_reference_id="max-benchmark",
    )
    if request.request_digest != MAXIMUM_REQUEST_DIGEST:
        raise BenchmarkError("maximum-resampling request digest does not match its lock")
    return request


def _measure_request(
    request: FunctionalProteotypeRequest,
    *,
    warmup_runs: int,
    measured_runs: int,
) -> tuple[str, int, tuple[float, ...], FunctionalProteotypeResult]:
    expected_digest: str | None = None
    expected_size: int | None = None
    latest_result: FunctionalProteotypeResult | None = None
    for _ in range(warmup_runs):
        result = analyze_functional_proteotype(request)
        latest_result = result
        result_size = len(canonical_json_bytes(result.model_dump(mode="json")))
        if expected_digest is None:
            expected_digest = result.result_digest
            expected_size = result_size
        elif result.result_digest != expected_digest or result_size != expected_size:
            raise BenchmarkError("warmup result digest or size was not deterministic")

    durations: list[float] = []
    for _ in range(measured_runs):
        started = perf_counter()
        result = analyze_functional_proteotype(request)
        latest_result = result
        durations.append(round(perf_counter() - started, ROUND_DIGITS_SECONDS))
        result_size = len(canonical_json_bytes(result.model_dump(mode="json")))
        if expected_digest is None:
            expected_digest = result.result_digest
            expected_size = result_size
        elif result.result_digest != expected_digest or result_size != expected_size:
            raise BenchmarkError("measured result digest or size was not deterministic")

    if expected_digest is None or expected_size is None or latest_result is None:
        raise BenchmarkError("benchmark produced no complete result receipt")
    return expected_digest, expected_size, tuple(durations), latest_result


def _validate_maximum_execution(result: FunctionalProteotypeResult) -> None:
    if not result.solver.converged:
        raise BenchmarkError("maximum-resampling solver did not converge")
    if result.provenance.bootstrap_replicates_used != MAXIMUM_BOOTSTRAP_REPLICATES:
        raise BenchmarkError("maximum-resampling bootstrap workload was incomplete")
    if result.provenance.permutation_replicates_used != MAXIMUM_PERMUTATION_REPLICATES:
        raise BenchmarkError("maximum-resampling permutation workload was incomplete")
    if len(result.axis_evidence) != MAXIMUM_AXIS_OUTPUT_COUNT:
        raise BenchmarkError("maximum-resampling axis workload was incomplete")
    if any(item.support.value != "supported" for item in result.axis_evidence):
        raise BenchmarkError("maximum-resampling axis workload unexpectedly abstained")
    if sum(len(item.ablations) for item in result.axis_evidence) != MAXIMUM_ABLATION_OUTPUT_COUNT:
        raise BenchmarkError("maximum-resampling ablation workload was incomplete")


def _run_in_process(
    *,
    warmup_runs: int = DEFAULT_WARMUP_RUNS,
    measured_runs: int = DEFAULT_MEASURED_RUNS,
) -> DemoPerformanceEvidence:
    """Run the full demo inside the dedicated benchmark executable."""

    _validate_run_counts(warmup_runs=warmup_runs, measured_runs=measured_runs)
    if sys.gettrace() is not None:
        raise BenchmarkError("performance evidence requires an uninstrumented process")

    request = synthetic_demo_request()
    profile = algorithm_profile()
    if np.__version__ != "2.5.2":
        raise BenchmarkError("performance evidence requires the profile-pinned NumPy version")
    request_bytes = len(canonical_json_bytes(request.model_dump(mode="json")))
    expected_digest, expected_size, measured, _result = _measure_request(
        request,
        warmup_runs=warmup_runs,
        measured_runs=measured_runs,
    )
    p95_seconds = nearest_rank_percentile(measured, P95_PERCENT)
    return DemoPerformanceEvidence(
        fixture_digest=request.request_digest,
        profile_digest=profile.profile_digest,
        result_digest=expected_digest,
        numpy_version="2.5.2",
        python_version=platform.python_version(),
        platform=platform.platform(),
        request_bytes=request_bytes,
        result_bytes=expected_size,
        warmup_runs=warmup_runs,
        measured_runs=measured_runs,
        durations_seconds=measured,
        p95_seconds=p95_seconds,
        passed=p95_seconds < DEMO_P95_THRESHOLD_SECONDS,
    )


def _run_maximum_resampling_in_process(
    *,
    warmup_runs: int = MAXIMUM_DEFAULT_WARMUP_RUNS,
    measured_runs: int = MAXIMUM_DEFAULT_MEASURED_RUNS,
) -> MaximumResamplingPerformanceEvidence:
    """Run all 600 active catalog proteins at both resampling maxima."""

    _validate_run_counts(warmup_runs=warmup_runs, measured_runs=measured_runs)
    if sys.gettrace() is not None:
        raise BenchmarkError("performance evidence requires an uninstrumented process")

    request = maximum_resampling_request()
    profile = algorithm_profile()
    if np.__version__ != "2.5.2":
        raise BenchmarkError("performance evidence requires the profile-pinned NumPy version")
    request_bytes = len(canonical_json_bytes(request.model_dump(mode="json")))
    if request_bytes != MAXIMUM_REQUEST_BYTES:
        raise BenchmarkError("maximum-resampling request size does not match its lock")
    expected_digest, expected_size, measured, result = _measure_request(
        request,
        warmup_runs=warmup_runs,
        measured_runs=measured_runs,
    )
    _validate_maximum_execution(result)
    p95_seconds = nearest_rank_percentile(measured, P95_PERCENT)
    return MaximumResamplingPerformanceEvidence(
        fixture_digest=request.request_digest,
        profile_digest=profile.profile_digest,
        result_digest=expected_digest,
        numpy_version="2.5.2",
        python_version=platform.python_version(),
        platform=platform.platform(),
        request_bytes=request_bytes,
        result_bytes=expected_size,
        warmup_runs=warmup_runs,
        measured_runs=measured_runs,
        durations_seconds=measured,
        p95_seconds=p95_seconds,
        passed=p95_seconds < MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS,
    )


def _fresh_process_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for variable in _COVERAGE_ENVIRONMENT_VARIABLES:
        environment.pop(variable, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def run_demo_benchmark(
    *,
    warmup_runs: int = DEFAULT_WARMUP_RUNS,
    measured_runs: int = DEFAULT_MEASURED_RUNS,
) -> DemoPerformanceEvidence:
    """Execute the benchmark in a fresh process and validate its receipt."""

    _validate_run_counts(warmup_runs=warmup_runs, measured_runs=measured_runs)
    command = (
        sys.executable,
        "-B",
        "-m",
        "benchmarks.research_gbm_functional_proteotype",
        "--warmup-runs",
        str(warmup_runs),
        "--measured-runs",
        str(measured_runs),
    )
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=_fresh_process_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=FRESH_PROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise BenchmarkError("fresh benchmark process exceeded its time limit") from error
    except OSError as error:
        raise BenchmarkError("fresh benchmark process could not be started") from error
    try:
        evidence = DemoPerformanceEvidence.model_validate_json(completed.stdout, strict=True)
    except ValueError as error:
        raise BenchmarkError("fresh benchmark process did not emit a valid receipt") from error
    if completed.returncode != (0 if evidence.passed else 1):
        raise BenchmarkError("fresh benchmark exit state disagrees with its receipt")
    return evidence


def run_maximum_resampling_benchmark(
    *,
    warmup_runs: int = MAXIMUM_DEFAULT_WARMUP_RUNS,
    measured_runs: int = MAXIMUM_DEFAULT_MEASURED_RUNS,
) -> MaximumResamplingPerformanceEvidence:
    """Execute the maximum-resampling gate in a fresh process."""

    _validate_run_counts(warmup_runs=warmup_runs, measured_runs=measured_runs)
    timeout_seconds = max(
        FRESH_PROCESS_TIMEOUT_SECONDS,
        (warmup_runs + measured_runs) * MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS
        + FRESH_PROCESS_STARTUP_ALLOWANCE_SECONDS,
    )
    command = (
        sys.executable,
        "-B",
        "-m",
        "benchmarks.research_gbm_functional_proteotype",
        "--scenario",
        MAXIMUM_RESAMPLING_SCENARIO,
        "--warmup-runs",
        str(warmup_runs),
        "--measured-runs",
        str(measured_runs),
    )
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=_fresh_process_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise BenchmarkError("fresh benchmark process exceeded its time limit") from error
    except OSError as error:
        raise BenchmarkError("fresh benchmark process could not be started") from error
    try:
        evidence = MaximumResamplingPerformanceEvidence.model_validate_json(
            completed.stdout,
            strict=True,
        )
    except ValueError as error:
        raise BenchmarkError("fresh benchmark process did not emit a valid receipt") from error
    if completed.returncode != (0 if evidence.passed else 1):
        raise BenchmarkError("fresh benchmark exit state disagrees with its receipt")
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(DEMO_SCENARIO, MAXIMUM_RESAMPLING_SCENARIO),
        default=DEMO_SCENARIO,
    )
    parser.add_argument("--warmup-runs", type=int, default=DEFAULT_WARMUP_RUNS)
    parser.add_argument("--measured-runs", type=int, default=DEFAULT_MEASURED_RUNS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    evidence: MaximumResamplingPerformanceEvidence | DemoPerformanceEvidence
    if arguments.scenario == MAXIMUM_RESAMPLING_SCENARIO:
        evidence = _run_maximum_resampling_in_process(
            warmup_runs=arguments.warmup_runs,
            measured_runs=arguments.measured_runs,
        )
    else:
        evidence = _run_in_process(
            warmup_runs=arguments.warmup_runs,
            measured_runs=arguments.measured_runs,
        )
    sys.stdout.buffer.write(canonical_json_bytes(evidence.model_dump(mode="json")) + b"\n")
    return 0 if evidence.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEMO_P95_THRESHOLD_SECONDS",
    "EVIDENCE_SCHEMA_VERSION",
    "EXECUTION_ISOLATION",
    "MAXIMUM_ABLATION_OUTPUT_COUNT",
    "MAXIMUM_AXIS_OUTPUT_COUNT",
    "MAXIMUM_BOOTSTRAP_REPLICATES",
    "MAXIMUM_OBSERVATION_COUNT",
    "MAXIMUM_PERMUTATION_REPLICATES",
    "MAXIMUM_REQUEST_DIGEST",
    "MAXIMUM_RESAMPLING_EVIDENCE_SCHEMA_VERSION",
    "MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS",
    "MAXIMUM_RESAMPLING_PROFILE",
    "MAXIMUM_RESAMPLING_SCENARIO",
    "BenchmarkError",
    "DemoPerformanceEvidence",
    "MaximumResamplingPerformanceEvidence",
    "main",
    "maximum_resampling_request",
    "nearest_rank_percentile",
    "run_demo_benchmark",
    "run_maximum_resampling_benchmark",
]
