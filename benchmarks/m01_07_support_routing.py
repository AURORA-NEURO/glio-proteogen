"""M01-07 public-router microbenchmark with a broad CI regression budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m01_07.run import build_scenario_request

from glio_proteogen.contracts.m01_07 import (
    CriterionDecision,
    RouteDecision,
    SupportDimension,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router import (
    route_support_request,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.250
EXPECTED_ASSESSMENT_COUNT = 8

pytestmark = pytest.mark.benchmark


def test_supported_public_router_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("supported")

    result = benchmark(route_support_request, request)

    benchmark.extra_info.update(
        {
            "boundary": "authorized support evidence to decision and remediation envelope",
            "criterion_count": len(request.profile.criteria),
            "evidence_count": len(request.evidence),
            "dimension_count": len(SupportDimension),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.decision is RouteDecision.SUPPORTED
    assert len(result.assessments) == EXPECTED_ASSESSMENT_COUNT
    assert all(
        item.decision is CriterionDecision.SUPPORTED and not item.blocks_route
        for item in result.assessments
    )
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
