"""M02-08 complete-chain ten-member public-packager benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_08.run import build_representative_release_fixture

from glio_proteogen.contracts.m02_08 import (
    M0208_ARCHIVE_MEMBER_COUNT,
    IdentificationReleaseDisposition,
)
from glio_proteogen.kernel.canonical_ustar import inspect_canonical_ustar
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging import (
    build_identification_release,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 1.500
EXPECTED_CALLER_ARTIFACTS = 8
EXPECTED_METADATA_RECORDS = 64

pytestmark = pytest.mark.benchmark


def test_representative_public_identification_release_latency(
    benchmark: BenchmarkFixture,
) -> None:
    fixture, verifier = build_representative_release_fixture()

    built = benchmark(
        build_identification_release,
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        verifier,
    )

    benchmark.extra_info.update(
        {
            "boundary": "genuine M02-01..M02-07 results to one canonical release archive",
            "caller_artifacts": len(fixture.artifacts),
            "archive_members": M0208_ARCHIVE_MEMBER_COUNT,
            "software_versions": len(fixture.request.software_versions),
            "reference_versions": len(fixture.request.reference_versions),
            "input_bytes": sum(len(value) for value in fixture.artifacts.values()),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert built.result.disposition is IdentificationReleaseDisposition.RELEASED
    assert built.package_bytes is not None
    assert len(fixture.artifacts) == EXPECTED_CALLER_ARTIFACTS
    descriptor = built.result.package_descriptor
    assert descriptor is not None
    assert descriptor.member_count == M0208_ARCHIVE_MEMBER_COUNT
    assert len(inspect_canonical_ustar(built.package_bytes)) == M0208_ARCHIVE_MEMBER_COUNT
    assert len(fixture.request.software_versions) == EXPECTED_METADATA_RECORDS
    assert len(fixture.request.reference_versions) == EXPECTED_METADATA_RECORDS
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
