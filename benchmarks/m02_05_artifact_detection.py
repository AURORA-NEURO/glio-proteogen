"""M02-05 representative identification-artifact batch benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_05.run import build_scenario_request

from benchmarks._module_validation import run_pytest_benchmark
from glio_proteogen.contracts.m02_05 import (
    DetectIdentificationArtifactsRequest,
    DetectionDisposition,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    detect_identification_artifacts,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

# The 24-result batch spans repeated typed validation and canonical receipt construction.
# A 750 ms ceiling retains a meaningful regression tripwire while tolerating the measured
# 360-517 ms fresh-process range on the Windows reference host.
MEAN_BUDGET_SECONDS = 0.750
BATCH_SIZE = 24
EXPECTED_FLAGS_PER_RESULT = 28

pytestmark = pytest.mark.benchmark


def _detect_batch(
    request: DetectIdentificationArtifactsRequest,
) -> tuple[tuple[DetectionDisposition, int, int], ...]:
    return tuple(
        (
            result.disposition,
            len(result.flags),
            len(result.exclusion_mask.excluded_target_ids),
        )
        for result in (detect_identification_artifacts(request) for _ in range(BATCH_SIZE))
    )


def test_representative_public_artifact_batch_latency(
    benchmark: BenchmarkFixture,
) -> None:
    request = build_scenario_request("seven_class_seeded")

    outcomes = benchmark(_detect_batch, request)

    benchmark.extra_info.update(
        {
            "boundary": "authorized identification-QC signals to artifact flags and mask",
            "batch_size": BATCH_SIZE,
            "artifact_classes": 7,
            "flags_per_result": EXPECTED_FLAGS_PER_RESULT,
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert (
        outcomes == ((DetectionDisposition.QUARANTINED, EXPECTED_FLAGS_PER_RESULT, 4),) * BATCH_SIZE
    )
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    """Run the locked representative artifact-detection batch workload."""

    return run_pytest_benchmark(
        module_id="GLIO-PROTEOGEN-M02-05",
        workload=test_representative_public_artifact_batch_latency,
        iterations=iterations,
        mean_budget_seconds=MEAN_BUDGET_SECONDS,
    )
