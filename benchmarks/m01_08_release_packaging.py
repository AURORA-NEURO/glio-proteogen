"""M01-08 public-packager microbenchmark with a broad CI tripwire."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m01_08.run import build_scenario

from glio_proteogen.contracts.m01_08 import ReleaseDisposition
from glio_proteogen.modules.c01_preanalytic.m01_08_release_packaging import (
    build_release_package,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.250
EXPECTED_ARTIFACT_COUNT = 3

pytestmark = pytest.mark.benchmark


def test_representative_public_packager_latency(benchmark: BenchmarkFixture) -> None:
    request, files = build_scenario("canonical")

    built = benchmark(build_release_package, request, files)

    benchmark.extra_info.update(
        {
            "boundary": "authorized declared artifacts to canonical release package",
            "artifact_count": len(request.artifacts),
            "input_bytes": sum(len(value) for value in files.values()),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert built.result.disposition is ReleaseDisposition.RELEASED
    assert built.result.package.artifact_count == EXPECTED_ARTIFACT_COUNT
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
