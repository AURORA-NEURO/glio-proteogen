"""M06-04 representative proxy and abstention microbenchmarks."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from evals.m06_04.run import build_scenario_request

from benchmarks._module_validation import run_pytest_benchmark
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
    feature_values = cast("tuple[object, ...]", request["feature_values"])

    benchmark.extra_info.update(
        {
            "boundary": "locked formal-state representation to declaration-only numeric proxy",
            "feature_count": len(feature_values),
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
    feature_values = cast("tuple[object, ...]", request["feature_values"])

    benchmark.extra_info.update(
        {
            "boundary": "unsupported model family to typed safe abstention",
            "feature_count": len(feature_values),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.status.value == "abstained"
    assert benchmark.stats is not None
    assert benchmark.stats.stats is not None
    assert benchmark.stats.stats.mean <= MEAN_BUDGET_SECONDS


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    """Run the locked representative probabilistic estimate workload."""

    return run_pytest_benchmark(
        module_id="GLIO-PROTEOGEN-M06-04",
        workload=test_proxy_estimate_latency,
        iterations=iterations,
        mean_budget_seconds=MEAN_BUDGET_SECONDS,
    )
