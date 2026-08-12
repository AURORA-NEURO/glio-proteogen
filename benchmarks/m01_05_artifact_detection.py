"""M01-05 public-engine microbenchmark with a broad CI regression budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m01_05.run import build_scenario_request

from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection import (
    detect_artifacts,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.250
EXPECTED_FLAG_COUNT = 56
EXPECTED_EXCLUDED_TARGET_COUNT = 4

pytestmark = pytest.mark.benchmark


def test_seeded_batch_public_engine_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("seeded_batch")

    result = benchmark(detect_artifacts, request)

    benchmark.extra_info.update(
        {
            "boundary": "authorized technical signals to artifact flags and mask",
            "rule_count": len(request.rules),
            "signal_count": len(request.signals),
            "flag_count": EXPECTED_FLAG_COUNT,
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert len(result.flags) == EXPECTED_FLAG_COUNT
    assert len(result.exclusion_mask.excluded_target_ids) == EXPECTED_EXCLUDED_TARGET_COUNT
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
