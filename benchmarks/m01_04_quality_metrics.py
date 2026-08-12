"""M01-04 public-engine microbenchmark with a broad CI regression budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m01_04.run import build_scenario_request

from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics import (
    compute_quality_profile,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.050
EXPECTED_METRIC_COUNT = 5

pytestmark = pytest.mark.benchmark


def test_representative_public_engine_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("complete")

    result = benchmark(compute_quality_profile, request)

    benchmark.extra_info.update(
        {
            "boundary": "authorized quality request to typed profile",
            "metric_count": len(request.metric_definitions),
            "observation_count": len(request.observations),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.disposition.value == "accepted"
    assert len(result.metrics) == EXPECTED_METRIC_COUNT
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
