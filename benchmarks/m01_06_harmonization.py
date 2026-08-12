"""M01-06 public-engine microbenchmark with a broad CI regression budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m01_06.run import build_scenario_request

from glio_proteogen.contracts.m01_06 import (
    DiagnosticStatus,
    HarmonizationDisposition,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization import (
    harmonize_observations,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.250
EXPECTED_VALUE_COUNT = 32
EXPECTED_STAGE_COUNT = 2
EXPECTED_INVARIANT_COUNT = 2

pytestmark = pytest.mark.benchmark


def test_supported_public_engine_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("supported")

    result = benchmark(harmonize_observations, request)

    benchmark.extra_info.update(
        {
            "boundary": "authorized observations to harmonized object and manifest",
            "observation_count": len(request.observations),
            "stage_count": len(request.profile.stages),
            "invariant_count": len(request.biological_invariants),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.disposition is HarmonizationDisposition.ACCEPTED
    assert len(result.values) == EXPECTED_VALUE_COUNT
    assert len(result.transformation_manifest.stages) == EXPECTED_STAGE_COUNT
    assert len(result.biological_invariant_diagnostics) == EXPECTED_INVARIANT_COUNT
    assert all(
        item.status is DiagnosticStatus.PASSED
        for item in (
            *result.technical_effect_diagnostics,
            *result.biological_invariant_diagnostics,
        )
    )
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
