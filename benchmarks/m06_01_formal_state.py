"""M06-01 representative formal-state validation microbenchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m06_01.run import build_scenario_request

from glio_proteogen.contracts.m06_01 import FormalStateValidationStatus
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema import (
    validate_formal_protein_state,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.250

pytestmark = pytest.mark.benchmark


def test_valid_formal_state_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("valid")
    result = benchmark(validate_formal_protein_state, request)

    benchmark.extra_info.update(
        {
            "boundary": "declared feature values to executable formal-state invariants",
            "invariant_count": len(request.state_schema.invariants),
            "feature_count": len(request.state_schema.features),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.status is FormalStateValidationStatus.VALID
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS


def test_abstained_formal_state_latency(benchmark: BenchmarkFixture) -> None:
    request = build_scenario_request("missing")
    result = benchmark(validate_formal_protein_state, request)

    benchmark.extra_info.update(
        {
            "boundary": "missing formal-state value to explicit safe abstention",
            "invariant_count": len(request.state_schema.invariants),
            "feature_count": len(request.state_schema.features),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.status is FormalStateValidationStatus.ABSTAINED
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
