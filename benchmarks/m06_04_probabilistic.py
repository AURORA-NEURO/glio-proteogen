"""M06-04 representative proxy and abstention microbenchmarks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m06_04.run import build_scenario_request

from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604Service,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.250

pytestmark = pytest.mark.benchmark


def test_proxy_estimate_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("valid")
    result = benchmark(M0604Service().estimate, request)

    benchmark.extra_info.update(
        {
            "boundary": "locked formal-state representation to declaration-only numeric proxy",
            "feature_count": len(request["feature_values"]),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.status.value == "estimated"
    assert benchmark.stats is not None
    assert benchmark.stats.stats is not None
    assert benchmark.stats.stats.mean <= MEAN_BUDGET_SECONDS


def test_abstention_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("learned")
    result = benchmark(M0604Service().estimate, request)

    benchmark.extra_info.update(
        {
            "boundary": "unsupported model family to typed safe abstention",
            "feature_count": len(request["feature_values"]),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.status.value == "abstained"
    assert benchmark.stats is not None
    assert benchmark.stats.stats is not None
    assert benchmark.stats.stats.mean <= MEAN_BUDGET_SECONDS
