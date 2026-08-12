"""M02-06 representative eight-stage identification-harmonization benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_06.run import build_representative_request

from glio_proteogen.contracts.m02_06 import (
    HarmonizationDisposition,
    HarmonizeIdentificationEvidenceRequest,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    harmonize_identification_evidence,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.500
EXPECTED_OBSERVATIONS = 128
EXPECTED_STAGES = 8
EXPECTED_BIOLOGICAL_CONTROLS = 2

pytestmark = pytest.mark.benchmark


def _harmonize(
    request: HarmonizeIdentificationEvidenceRequest,
) -> tuple[HarmonizationDisposition, int, int, int]:
    result = harmonize_identification_evidence(request)
    return (
        result.disposition,
        len(result.values),
        len(result.transformation_manifest.stages),
        len(result.biological_invariant_diagnostics),
    )


def test_representative_public_identification_harmonization_latency(
    benchmark: BenchmarkFixture,
) -> None:
    request = build_representative_request()
    assert len(request.observations) == EXPECTED_OBSERVATIONS
    assert len(request.profile.stages) == EXPECTED_STAGES
    assert len(request.biological_controls) == EXPECTED_BIOLOGICAL_CONTROLS

    outcome = benchmark(_harmonize, request)

    benchmark.extra_info.update(
        {
            "boundary": "exact C02 prerequisites and typed abundance to harmonized object",
            "observations": EXPECTED_OBSERVATIONS,
            "stages": EXPECTED_STAGES,
            "biological_controls": EXPECTED_BIOLOGICAL_CONTROLS,
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert outcome == (
        HarmonizationDisposition.ACCEPTED,
        EXPECTED_OBSERVATIONS,
        EXPECTED_STAGES,
        EXPECTED_BIOLOGICAL_CONTROLS,
    )
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
