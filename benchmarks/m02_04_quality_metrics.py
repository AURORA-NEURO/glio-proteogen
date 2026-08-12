"""M02-04 representative identification-quality batch benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_04.run import build_scenario_request

from glio_proteogen.contracts.m02_04 import (
    ComputeIdentificationQualityRequest,
    IdentificationQualityDisposition,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    compute_identification_quality,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.500
BATCH_SIZE = 32

pytestmark = pytest.mark.benchmark


def _compute_batch(
    request: ComputeIdentificationQualityRequest,
) -> tuple[IdentificationQualityDisposition, ...]:
    return tuple(
        compute_identification_quality(request).disposition
        for _ in range(BATCH_SIZE)
    )


def test_representative_public_quality_batch_latency(
    benchmark: BenchmarkFixture,
) -> None:
    request = build_scenario_request()

    dispositions = benchmark(_compute_batch, request)

    benchmark.extra_info.update(
        {
            "boundary": "six typed identification observations to quality profiles",
            "batch_size": BATCH_SIZE,
            "metrics_per_request": len(request.observations),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert dispositions == (IdentificationQualityDisposition.ACCEPTED,) * BATCH_SIZE
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
