"""M02-07 representative maximum-envelope public-router benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_07.run import build_representative_request

from glio_proteogen.contracts.m02_07 import (
    M0207_MAX_ENVELOPES,
    DimensionSupportDecision,
    EnvelopeSupportDecision,
    IdentificationSupportDisposition,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    route_identification_support,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.500
EXPECTED_DIMENSIONS = 8

pytestmark = pytest.mark.benchmark


def test_representative_public_identification_support_router_latency(
    benchmark: BenchmarkFixture,
) -> None:
    request = build_representative_request()
    assert len(request.profile.envelopes) == M0207_MAX_ENVELOPES

    result = benchmark(route_identification_support, request)

    benchmark.extra_info.update(
        {
            "boundary": "compact C02 receipts and declarations to one joint-envelope route",
            "envelopes": M0207_MAX_ENVELOPES,
            "dimensions_per_envelope": EXPECTED_DIMENSIONS,
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.disposition is IdentificationSupportDisposition.SUPPORTED
    assert len(result.matched_envelope_ids) == M0207_MAX_ENVELOPES
    assert len(result.envelope_assessments) == M0207_MAX_ENVELOPES
    assert all(
        assessment.decision is EnvelopeSupportDecision.CONFIRMED
        and len(assessment.dimensions) == EXPECTED_DIMENSIONS
        and all(
            dimension.decision is DimensionSupportDecision.SUPPORTED
            for dimension in assessment.dimensions
        )
        for assessment in result.envelope_assessments
    )
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
