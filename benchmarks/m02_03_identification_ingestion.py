"""M02-03 representative six-role ingestion batch benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_03.run import ScenarioSubmission, build_representative_submission

from glio_proteogen.contracts.m01_03 import RawInputDisposition
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import (
    evaluate_identification_raw_ingestion,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.500
BATCH_SIZE = 16

pytestmark = pytest.mark.benchmark


def _ingest_batch(
    submission: ScenarioSubmission,
) -> tuple[RawInputDisposition, ...]:
    return tuple(
        evaluate_identification_raw_ingestion(
            submission.request,
            submission.sources,
            submission.filenames,
        ).disposition
        for _ in range(BATCH_SIZE)
    )


def test_representative_six_role_batch_latency(benchmark: BenchmarkFixture) -> None:
    submission = build_representative_submission()

    dispositions = benchmark(_ingest_batch, submission)

    benchmark.extra_info.update(
        {
            "boundary": "six role-tagged raw inputs to metadata-only ingestion result",
            "batch_size": BATCH_SIZE,
            "sources_per_request": len(submission.request.sources),
            "source_bytes_per_request": sum(len(item) for item in submission.sources.values()),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert dispositions == (RawInputDisposition.ACCEPTED,) * BATCH_SIZE
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
