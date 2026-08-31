"""M01-03 public parser microbenchmarks with broad CI regression budgets."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from benchmarks._module_validation import SmokeBenchmark, run_pytest_benchmark
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import parse_raw_input

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Protocol, TypeVar

    _ResultT = TypeVar("_ResultT")

    class _TimingStatistics(Protocol):
        mean: float

    class _BenchmarkStatistics(Protocol):
        stats: _TimingStatistics

    class BenchmarkFixture(Protocol):
        stats: _BenchmarkStatistics
        extra_info: dict[str, object]

        def __call__(
            self,
            operation: Callable[..., _ResultT],
            *args: object,
            **kwargs: object,
        ) -> _ResultT: ...


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "m01_03"
MEAN_BUDGET_SECONDS = 0.010

pytestmark = pytest.mark.benchmark


@pytest.mark.parametrize(
    ("fixture", "expected_format", "expected_records"),
    [
        ("mzml.valid.mzML", "mzML", 1),
        ("mztab_m.valid.mzTab", "mzTab-M", 4),
        ("variants.valid.vcf", "VCF", 1),
        ("proteins.valid.fasta.gz", "FASTA", 2),
    ],
)
def test_public_ingestion_latency(
    benchmark: BenchmarkFixture,
    fixture: str,
    expected_format: str,
    expected_records: int,
) -> None:
    payload = (FIXTURES / fixture).read_bytes()

    result = benchmark(
        parse_raw_input,
        payload,
        source_id=f"source.synthetic.benchmark.{expected_format.casefold()}",
        filename=fixture,
    )

    benchmark.extra_info.update(
        {
            "boundary": "raw bytes to metadata-only typed descriptor",
            "format": expected_format,
            "source_bytes": len(payload),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.disposition.value == "accepted"
    assert result.detected is not None
    assert result.detected.format.value == expected_format
    assert result.record_count == expected_records
    assert benchmark.stats.stats.mean <= MEAN_BUDGET_SECONDS


def _run_reference_ingestion(benchmark: SmokeBenchmark) -> None:
    test_public_ingestion_latency(
        cast("BenchmarkFixture", benchmark),
        "mzml.valid.mzML",
        "mzML",
        1,
    )


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    """Run the locked representative mzML ingestion workload."""

    return run_pytest_benchmark(
        module_id="GLIO-PROTEOGEN-M01-03",
        workload=_run_reference_ingestion,
        iterations=iterations,
        mean_budget_seconds=MEAN_BUDGET_SECONDS,
    )
