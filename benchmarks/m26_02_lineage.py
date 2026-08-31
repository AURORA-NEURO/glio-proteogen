"""Locked microbenchmark wrapper for M26-02 lineage construction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evals.m26_02.fixture import request

from benchmarks._module_validation import run_pytest_benchmark
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service import (
    M2602LineageService,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 2.0


def test_m26_02_lineage_construction(benchmark: BenchmarkFixture) -> None:
    service = M2602LineageService()
    candidate = request()
    result = benchmark(service.execute, candidate)
    assert result.status.value == "built"


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    """Run the locked representative lineage-construction workload."""

    return run_pytest_benchmark(
        module_id="GLIO-PROTEOGEN-M26-02",
        workload=test_m26_02_lineage_construction,
        iterations=iterations,
        mean_budget_seconds=MEAN_BUDGET_SECONDS,
    )
