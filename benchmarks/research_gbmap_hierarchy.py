"""Deterministic GBmap hierarchy coordinate-fit regression benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np
import pytest

from benchmarks._module_validation import run_pytest_benchmark
from glio_proteogen.research.gbmap_deconvolution.hierarchy import (
    HierarchySolverConfiguration,
    fit_lineage_hierarchy,
    verify_hierarchy_trace,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS: Final = 0.5
EXPECTED_OBJECTIVE: Final = 0.38205654146780993
DONOR_COUNT: Final = 16
STUDY_COUNT: Final = 4
GENE_COUNT: Final = 64

pytestmark = pytest.mark.benchmark

_RANDOM = np.random.default_rng(20260830)
_PROBABILITIES = np.linspace(1.0, 2.0, GENE_COUNT, dtype=np.float64)
_PROBABILITIES /= np.sum(_PROBABILITIES, dtype=np.float64)
_COUNTS = np.stack(tuple(_RANDOM.multinomial(10_000, _PROBABILITIES) for _ in range(DONOR_COUNT)))
_STUDIES = tuple(f"study-{donor // 4}" for donor in range(DONOR_COUNT))
_BACKGROUND = np.full(GENE_COUNT, 1.0 / GENE_COUNT, dtype=np.float64)
_CONFIGURATION = HierarchySolverConfiguration(
    max_outer_iterations=1,
    max_study_sweeps=1,
    max_signature_iterations=4,
    max_golden_iterations=4,
    golden_log_tolerance=1.0e-4,
    kkt_tolerance=1.0e-5,
)


def test_representative_gbmap_hierarchy_latency(benchmark: BenchmarkFixture) -> None:
    """Time a multi-study, marker-scale coordinate pass with exact DM losses."""

    fit = benchmark(
        fit_lineage_hierarchy,
        _COUNTS,
        _STUDIES,
        _BACKGROUND,
        shrinkage=2.0,
        configuration=_CONFIGURATION,
    )

    benchmark.extra_info.update(
        {
            "boundary": "validated donor aggregates to one deterministic hierarchy pass",
            "donor_count": DONOR_COUNT,
            "study_count": STUDY_COUNT,
            "gene_count": GENE_COUNT,
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert fit.objective == EXPECTED_OBJECTIVE
    assert verify_hierarchy_trace(fit)
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS


def run_benchmark(iterations: int = 3) -> dict[str, object]:
    """Run the locked GBmap hierarchy regression workload."""

    return run_pytest_benchmark(
        module_id="GLIO-PROTEOGEN-RESEARCH-GBMAP-HIERARCHY",
        workload=test_representative_gbmap_hierarchy_latency,
        iterations=iterations,
        mean_budget_seconds=MEAN_BUDGET_SECONDS,
    )


__all__ = ["run_benchmark"]
