"""M05-07 representative public support-router microbenchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m05_07.run import build_scenario_request

from glio_proteogen.contracts.m05_07 import (
    M0507_DIMENSION_COUNT,
    PtmLocalizationSupportDisposition,
)
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router import (
    route_ptm_localization_support,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.250
EXPECTED_MULTIPLE_FAILURES = 2

pytestmark = pytest.mark.benchmark


def test_supported_public_router_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("supported")

    result = benchmark(route_ptm_localization_support, request)

    benchmark.extra_info.update(
        {
            "boundary": "eight closed PTM-localization support dimensions to safe disposition",
            "dimension_count": M0507_DIMENSION_COUNT,
            "fixture": "synthetic_nonclinical",
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.disposition is PtmLocalizationSupportDisposition.SUPPORTED
    assert len(result.request.declared_facts) == M0507_DIMENSION_COUNT
    assert not result.receipt.unsupported_dimensions
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS


def test_unsupported_public_router_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("multiple")

    result = benchmark(route_ptm_localization_support, request)

    benchmark.extra_info.update(
        {
            "boundary": "multiple unsupported dimensions to canonical abstention",
            "dimension_count": M0507_DIMENSION_COUNT,
            "fixture": "synthetic_nonclinical",
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.disposition is PtmLocalizationSupportDisposition.ABSTAINED
    assert len(result.receipt.unsupported_dimensions) == EXPECTED_MULTIPLE_FAILURES
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
