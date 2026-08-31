"""Executable performance and memory gate for the research ECGI engine.

The two fixtures are deliberately part of the evidence contract.  ``demo-64`` is
the public 64-node synthetic workbench request.  ``maximum-bounds`` reaches every
structural input bound named by the research profile: 256 nodes, 2,048 edges,
4,096 observations, and 128 kinase nodes. It also retains the algorithm defaults
of 64 bootstraps and 256 kinase permutations, preventing the structural gate from
reducing the normal uncertainty workload.

The public gate always launches a fresh, uninstrumented Python process. Each
scenario reports the operating system's lifetime peak resident-set size for
that executable process; memory already resident in a pytest, coverage, or
application host is never attributed to ECGI.
"""

# ruff: noqa: C901, PLR2004, TC003, TRY003

from __future__ import annotations

import argparse
import ctypes
import gc
import importlib
import math
import os
import platform
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter
from typing import Final, Literal, Self

import numpy as np
from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, Sha256Digest
from glio_proteogen.research.proteogenomic_state import (
    MAX_EDGES,
    MAX_KINASES,
    MAX_NODES,
    MAX_OBSERVATIONS,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    EdgeKind,
    EvidenceModality,
    EvidenceObservation,
    EvidenceState,
    GraphEdge,
    GraphNode,
    NodeKind,
    ProteogenomicStateRequest,
    algorithm_profile,
    analyze_proteogenomic_state,
    synthetic_demo_request,
)
from glio_proteogen.research.proteogenomic_state.canonical import (
    canonical_json_bytes,
    sha256_digest,
)

EVIDENCE_SCHEMA_VERSION: Final = "glio-ecgi-performance/1.1.0"
FIXTURE_GENERATION_VERSION: Final = "maximum-structural-bounds/1.0.0"
EXECUTION_ISOLATION: Final = "fresh-process"
MEMORY_METRIC: Final = "fresh-process-lifetime-peak-rss"
DEMO_P95_THRESHOLD_SECONDS = 2.0
MAXIMUM_P95_THRESHOLD_SECONDS = 10.0
PEAK_MEMORY_THRESHOLD_MIB = 256.0
DEFAULT_WARMUP_RUNS = 1
DEFAULT_DEMO_RUNS = 5
DEFAULT_MAXIMUM_RUNS = 3
MINIMUM_BOOTSTRAPS = 8
MINIMUM_PERMUTATIONS = 32
WORKLOAD_BOOTSTRAPS = 64
WORKLOAD_PERMUTATIONS = 256
MIB = 1_024 * 1_024
P95_PERCENT = 95
PERCENT_DENOMINATOR = 100
ROUND_DIGITS_SECONDS = 6
ROUND_DIGITS_MEMORY = 3
FRESH_PROCESS_TIMEOUT_SECONDS = 180.0
MAXIMUM_FIXTURE_DIGEST = "sha256:e95231465caebf2753823b57f670a27a8a1c32a5c1618d1cac75cc07186825cb"
_MAXIMUM_SOURCE_DIGEST = sha256_digest(
    {"fixture": FIXTURE_GENERATION_VERSION, "source": "synthetic"}
)
_COVERAGE_ENVIRONMENT_VARIABLES = (
    "COVERAGE_PROCESS_START",
    "COV_CORE_SOURCE",
    "COV_CORE_CONFIG",
    "COV_CORE_DATAFILE",
    "COV_CORE_BRANCH",
)


class BenchmarkError(RuntimeError):
    """Raised when a benchmark fixture or deterministic replay invariant fails."""


class ScenarioEvidence(FrozenModel):
    """Machine-checkable evidence for one bounded ECGI benchmark scenario."""

    scenario: Literal["demo-64", "maximum-bounds"]
    fixture_digest: Sha256Digest
    result_digest: Sha256Digest
    node_count: int = Field(ge=1, le=MAX_NODES)
    edge_count: int = Field(ge=0, le=MAX_EDGES)
    observation_count: int = Field(ge=0, le=MAX_OBSERVATIONS)
    kinase_count: int = Field(ge=0, le=MAX_KINASES)
    bootstrap_replicates: int = Field(ge=MINIMUM_BOOTSTRAPS)
    permutation_replicates: int = Field(ge=MINIMUM_PERMUTATIONS)
    request_bytes: int = Field(gt=0, le=MAX_REQUEST_BYTES)
    result_bytes: int = Field(gt=0, le=MAX_RESULT_BYTES)
    warmup_runs: int = Field(ge=0)
    measured_runs: int = Field(gt=0)
    durations_seconds: tuple[float, ...] = Field(min_length=1)
    p95_seconds: float = Field(ge=0.0)
    p95_threshold_seconds: float = Field(gt=0.0)
    peak_memory_mib: float = Field(gt=0.0)
    peak_memory_threshold_mib: float = Field(gt=0.0)
    passed: bool

    @model_validator(mode="after")
    def evidence_is_internally_consistent(self) -> Self:
        if len(self.durations_seconds) != self.measured_runs:
            raise ValueError("measured run count must equal the duration count")
        if not all(math.isfinite(value) and value >= 0.0 for value in self.durations_seconds):
            raise ValueError("durations must be finite and non-negative")
        expected_p95 = nearest_rank_percentile(self.durations_seconds, P95_PERCENT)
        if not math.isclose(self.p95_seconds, expected_p95, abs_tol=10**-ROUND_DIGITS_SECONDS):
            raise ValueError("reported p95 does not match the measured durations")
        expected_pass = (
            self.p95_seconds < self.p95_threshold_seconds
            and self.peak_memory_mib < self.peak_memory_threshold_mib
        )
        if self.passed is not expected_pass:
            raise ValueError("scenario pass state must be derived from strict thresholds")
        if self.scenario == "demo-64" and self.node_count != 64:
            raise ValueError("the demo benchmark must contain exactly 64 nodes")
        if self.scenario == "maximum-bounds" and (
            self.node_count,
            self.edge_count,
            self.observation_count,
            self.kinase_count,
        ) != (MAX_NODES, MAX_EDGES, MAX_OBSERVATIONS, MAX_KINASES):
            raise ValueError("the maximum benchmark must reach every structural bound")
        return self


class PerformanceEvidence(FrozenModel):
    """Portable benchmark receipt consumed by CI and retained as an artifact."""

    schema_version: Literal["glio-ecgi-performance/1.1.0"] = EVIDENCE_SCHEMA_VERSION
    fixture_generation_version: Literal["maximum-structural-bounds/1.0.0"] = (
        FIXTURE_GENERATION_VERSION
    )
    execution_isolation: Literal["fresh-process"] = EXECUTION_ISOLATION
    memory_metric: Literal["fresh-process-lifetime-peak-rss"] = MEMORY_METRIC
    profile_digest: Sha256Digest
    numpy_version: NonEmptyStr
    python_version: NonEmptyStr
    platform: NonEmptyStr
    scenarios: tuple[ScenarioEvidence, ScenarioEvidence]
    passed: bool

    @model_validator(mode="after")
    def receipt_is_complete(self) -> Self:
        names = tuple(item.scenario for item in self.scenarios)
        if names != ("demo-64", "maximum-bounds"):
            raise ValueError("performance evidence must contain both scenarios in order")
        if self.passed is not all(item.passed for item in self.scenarios):
            raise ValueError("receipt pass state must be derived from scenario gates")
        return self


def nearest_rank_percentile(values: Sequence[float], percentile: int) -> float:
    """Return a deterministic nearest-rank percentile from non-empty observations."""

    if not values:
        raise ValueError("percentile requires at least one value")
    if not 1 <= percentile <= PERCENT_DENOMINATOR:
        raise ValueError("percentile must be in [1, 100]")
    ordered = sorted(values)
    rank = math.ceil(percentile * len(ordered) / PERCENT_DENOMINATOR)
    return float(ordered[rank - 1])


def _build_maximum_request() -> ProteogenomicStateRequest:
    kinases = tuple(
        GraphNode(
            node_id=f"kinase.maximum.K{index:03d}",
            kind=NodeKind.KINASE,
            display_name=f"Synthetic kinase K{index:03d}",
        )
        for index in range(MAX_KINASES)
    )
    phosphosites = tuple(
        GraphNode(
            node_id=f"phosphosite.maximum.S{index:03d}",
            kind=NodeKind.PHOSPHOSITE,
            display_name=f"Synthetic phosphosite S{index:03d}",
        )
        for index in range(MAX_NODES - MAX_KINASES)
    )
    site_count = len(phosphosites)
    substrates_per_kinase = MAX_EDGES // MAX_KINASES
    edges = tuple(
        GraphEdge(
            edge_id=f"edge.maximum.K{kinase_index:03d}.E{edge_index:02d}",
            source_id=kinases[kinase_index].node_id,
            target_id=phosphosites[(kinase_index * 7 + edge_index * 11) % site_count].node_id,
            kind=EdgeKind.KINASE_SUBSTRATE,
            sign=-1 if (kinase_index + edge_index) % 5 == 0 else 1,
            weight=0.5 + ((kinase_index + edge_index) % 8) * 0.125,
        )
        for kinase_index in range(MAX_KINASES)
        for edge_index in range(substrates_per_kinase)
    )
    observations_per_site = MAX_OBSERVATIONS // site_count
    observations = tuple(
        EvidenceObservation(
            observation_id=f"observation.maximum.S{site_index:03d}.R{replicate:02d}",
            node_id=phosphosites[site_index].node_id,
            modality=(
                EvidenceModality.PHOSPHOPROTEOMICS
                if replicate % 2 == 0
                else EvidenceModality.PROTEOMICS
            ),
            state=EvidenceState.OBSERVED,
            standardized_effect=(
                ((site_index * 37) % 101 - 50) / 25.0 + ((replicate * 13) % 17 - 8) / 100.0
            ),
            standard_error=0.18 + (replicate % 5) * 0.025,
            quality_weight=0.72 + (replicate % 8) * 0.035,
            provenance_digest=_MAXIMUM_SOURCE_DIGEST,
        )
        for site_index in range(site_count)
        for replicate in range(observations_per_site)
    )
    return ProteogenomicStateRequest(
        sample_id="ecgi.maximum.fixture.v1",
        nodes=kinases + phosphosites,
        edges=edges,
        observations=observations,
        bootstrap_replicates=WORKLOAD_BOOTSTRAPS,
        permutation_replicates=WORKLOAD_PERMUTATIONS,
    )


def build_maximum_request() -> ProteogenomicStateRequest:
    """Build and verify the immutable maximum structural-bound fixture."""

    request = _build_maximum_request()
    if request.request_digest != MAXIMUM_FIXTURE_DIGEST:
        raise BenchmarkError(
            "maximum fixture digest changed; review and explicitly relock the fixture"
        )
    return request


def _windows_rss_bytes() -> int:
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = (
            ("cb", ctypes.c_ulong),
            ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        )

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info = psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    get_process_memory_info.restype = ctypes.c_int
    if not get_process_memory_info(get_current_process(), ctypes.byref(counters), counters.cb):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return int(counters.peak_working_set_size)


def _process_peak_rss_bytes() -> int:
    runtime_system = platform.system()
    if runtime_system == "Windows":
        return _windows_rss_bytes()
    resource_module = importlib.import_module("resource")
    usage = resource_module.getrusage(resource_module.RUSAGE_SELF)
    maximum_rss = int(usage.ru_maxrss)
    return maximum_rss if runtime_system == "Darwin" else maximum_rss * 1_024


def _measure_peak_rss(
    run: Callable[[], tuple[tuple[float, ...], str, int]],
) -> tuple[tuple[float, ...], str, int, int]:
    peak_before = _process_peak_rss_bytes()
    durations, result_digest, result_bytes = run()
    peak_after = _process_peak_rss_bytes()
    return durations, result_digest, result_bytes, max(peak_before, peak_after)


def _run_scenario(
    *,
    scenario: Literal["demo-64", "maximum-bounds"],
    request: ProteogenomicStateRequest,
    p95_threshold_seconds: float,
    warmup_runs: int,
    measured_runs: int,
) -> ScenarioEvidence:
    expected_result_digest: str | None = None
    for _ in range(warmup_runs):
        result = analyze_proteogenomic_state(request)
        if expected_result_digest is None:
            expected_result_digest = result.result_digest
        elif result.result_digest != expected_result_digest:
            raise BenchmarkError("warmup analysis was not deterministic")
    if warmup_runs:
        del result
    gc.collect()

    def measured() -> tuple[tuple[float, ...], str, int]:
        nonlocal expected_result_digest
        durations: list[float] = []
        result_bytes: int | None = None
        for _ in range(measured_runs):
            started = perf_counter()
            current = analyze_proteogenomic_state(request)
            elapsed = perf_counter() - started
            durations.append(round(elapsed, ROUND_DIGITS_SECONDS))
            if expected_result_digest is None:
                expected_result_digest = current.result_digest
            elif current.result_digest != expected_result_digest:
                raise BenchmarkError("measured analysis was not deterministic")
            current_result_bytes = len(canonical_json_bytes(current.model_dump(mode="json")))
            if result_bytes is None:
                result_bytes = current_result_bytes
            elif current_result_bytes != result_bytes:
                raise BenchmarkError("measured result size was not deterministic")
        if expected_result_digest is None or result_bytes is None:
            raise BenchmarkError("benchmark produced no complete result receipt")
        return tuple(durations), expected_result_digest, result_bytes

    durations, result_digest, result_bytes, peak_rss_bytes = _measure_peak_rss(measured)
    p95_seconds = nearest_rank_percentile(durations, P95_PERCENT)
    peak_memory_mib = round(peak_rss_bytes / MIB, ROUND_DIGITS_MEMORY)
    passed = p95_seconds < p95_threshold_seconds and peak_memory_mib < PEAK_MEMORY_THRESHOLD_MIB
    return ScenarioEvidence(
        scenario=scenario,
        fixture_digest=request.request_digest,
        result_digest=result_digest,
        node_count=len(request.nodes),
        edge_count=len(request.edges),
        observation_count=len(request.observations),
        kinase_count=sum(node.kind is NodeKind.KINASE for node in request.nodes),
        bootstrap_replicates=request.bootstrap_replicates,
        permutation_replicates=request.permutation_replicates,
        request_bytes=len(canonical_json_bytes(request.model_dump(mode="json"))),
        result_bytes=result_bytes,
        warmup_runs=warmup_runs,
        measured_runs=measured_runs,
        durations_seconds=durations,
        p95_seconds=p95_seconds,
        p95_threshold_seconds=p95_threshold_seconds,
        peak_memory_mib=peak_memory_mib,
        peak_memory_threshold_mib=PEAK_MEMORY_THRESHOLD_MIB,
        passed=passed,
    )


def _validate_run_counts(*, warmup_runs: int, demo_runs: int, maximum_runs: int) -> None:
    if warmup_runs < 0 or demo_runs < 1 or maximum_runs < 1:
        raise ValueError("warmups must be non-negative and measured runs must be positive")


def _run_performance_gate_in_process(
    *,
    warmup_runs: int = DEFAULT_WARMUP_RUNS,
    demo_runs: int = DEFAULT_DEMO_RUNS,
    maximum_runs: int = DEFAULT_MAXIMUM_RUNS,
) -> PerformanceEvidence:
    """Execute both scenarios inside a newly started benchmark executable."""

    _validate_run_counts(
        warmup_runs=warmup_runs,
        demo_runs=demo_runs,
        maximum_runs=maximum_runs,
    )
    if sys.gettrace() is not None:
        raise BenchmarkError("performance evidence requires an uninstrumented process")
    demo_request = synthetic_demo_request()
    demo_evidence = _run_scenario(
        scenario="demo-64",
        request=demo_request,
        p95_threshold_seconds=DEMO_P95_THRESHOLD_SECONDS,
        warmup_runs=warmup_runs,
        measured_runs=demo_runs,
    )
    del demo_request
    gc.collect()
    maximum_request = build_maximum_request()
    maximum_evidence = _run_scenario(
        scenario="maximum-bounds",
        request=maximum_request,
        p95_threshold_seconds=MAXIMUM_P95_THRESHOLD_SECONDS,
        warmup_runs=warmup_runs,
        measured_runs=maximum_runs,
    )
    scenarios = (demo_evidence, maximum_evidence)
    return PerformanceEvidence(
        profile_digest=algorithm_profile().profile_digest,
        numpy_version=np.__version__,
        python_version=platform.python_version(),
        platform=platform.platform(),
        scenarios=scenarios,
        passed=all(item.passed for item in scenarios),
    )


def _fresh_process_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for variable in _COVERAGE_ENVIRONMENT_VARIABLES:
        environment.pop(variable, None)
    return environment


def run_performance_gate(
    *,
    warmup_runs: int = DEFAULT_WARMUP_RUNS,
    demo_runs: int = DEFAULT_DEMO_RUNS,
    maximum_runs: int = DEFAULT_MAXIMUM_RUNS,
) -> PerformanceEvidence:
    """Run the acceptance gate in a fresh process and validate its receipt.

    Absolute resident-set size is meaningful only when unrelated imports and
    allocations cannot pre-populate the measured process. Coverage subprocess
    hooks are therefore removed from the child environment, and the child fails
    closed if any trace function is active.
    """

    _validate_run_counts(
        warmup_runs=warmup_runs,
        demo_runs=demo_runs,
        maximum_runs=maximum_runs,
    )
    command = (
        sys.executable,
        "-m",
        "benchmarks.research_proteogenomic_state",
        "--warmup-runs",
        str(warmup_runs),
        "--demo-runs",
        str(demo_runs),
        "--maximum-runs",
        str(maximum_runs),
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
        evidence = PerformanceEvidence.model_validate_json(completed.stdout, strict=True)
    except ValueError as error:
        raise BenchmarkError("fresh benchmark process did not emit a valid receipt") from error
    expected_return_code = 0 if evidence.passed else 1
    if completed.returncode != expected_return_code:
        raise BenchmarkError("fresh benchmark process exit state disagrees with its receipt")
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup-runs", type=int, default=DEFAULT_WARMUP_RUNS)
    parser.add_argument("--demo-runs", type=int, default=DEFAULT_DEMO_RUNS)
    parser.add_argument("--maximum-runs", type=int, default=DEFAULT_MAXIMUM_RUNS)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    evidence = _run_performance_gate_in_process(
        warmup_runs=arguments.warmup_runs,
        demo_runs=arguments.demo_runs,
        maximum_runs=arguments.maximum_runs,
    )
    payload = canonical_json_bytes(evidence.model_dump(mode="json")) + b"\n"
    if arguments.output is not None:
        arguments.output.write_bytes(payload)
    sys.stdout.buffer.write(payload)
    return 0 if evidence.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEMO_P95_THRESHOLD_SECONDS",
    "EVIDENCE_SCHEMA_VERSION",
    "EXECUTION_ISOLATION",
    "FIXTURE_GENERATION_VERSION",
    "MAXIMUM_FIXTURE_DIGEST",
    "MAXIMUM_P95_THRESHOLD_SECONDS",
    "MEMORY_METRIC",
    "PEAK_MEMORY_THRESHOLD_MIB",
    "BenchmarkError",
    "PerformanceEvidence",
    "ScenarioEvidence",
    "build_maximum_request",
    "main",
    "nearest_rank_percentile",
    "run_performance_gate",
]
