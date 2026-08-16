"""Locked microbenchmark wrapper for M26-02 lineage construction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evals.m26_02.fixture import request

from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service import (
    M2602LineageService,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture


def test_m26_02_lineage_construction(benchmark: BenchmarkFixture) -> None:
    service = M2602LineageService()
    candidate = request()
    result = benchmark(service.execute, candidate)
    assert result.status.value == "built"
