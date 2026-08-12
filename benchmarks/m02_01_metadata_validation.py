"""M02-01 representative batch-validator benchmark with a broad CI tripwire."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_01.run import build_scenario_request

from glio_proteogen.contracts.m02_01 import ConformanceDisposition
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    evaluate_conformance,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

    from glio_proteogen.contracts.m02_01 import EvaluateConformanceRequest

MEAN_BUDGET_SECONDS = 0.250
BATCH_SIZE = 32

pytestmark = pytest.mark.benchmark


def _validate_batch(
    batch: tuple[EvaluateConformanceRequest, ...],
) -> tuple[ConformanceDisposition, ...]:
    return tuple(evaluate_conformance(request).disposition for request in batch)


def test_representative_public_batch_validator_latency(
    benchmark: BenchmarkFixture,
) -> None:
    request = build_scenario_request("canonical")
    batch = tuple(request for _ in range(BATCH_SIZE))

    dispositions = benchmark(_validate_batch, batch)

    benchmark.extra_info.update(
        {
            "boundary": "pinned synthetic metadata batch to deterministic conformance states",
            "batch_size": BATCH_SIZE,
            "fields_per_record": len(request.protocol_schema.fields),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert dispositions == (ConformanceDisposition.CONFORMANT,) * BATCH_SIZE
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
