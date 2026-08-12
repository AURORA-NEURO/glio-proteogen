"""M02-05 representative identification-artifact batch benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_05.run import build_scenario_request

from glio_proteogen.contracts.m02_05 import (
    DetectIdentificationArtifactsRequest,
    DetectionDisposition,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    detect_identification_artifacts,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.500
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
