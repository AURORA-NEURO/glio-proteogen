"""Bounded public-service benchmark for M04-08 release packaging."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).parents[2]))

from evals.m04_08.run import DeterministicVerifier, _fixture
from glio_proteogen.contracts.m04_08 import ProteoformReleaseDisposition
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    build_proteoform_release,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M04-08"
DEFAULT_ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def _percentile(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def benchmark(iterations: int = DEFAULT_ITERATIONS) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    fixture = _fixture()

    # Warm the import/cache path outside the timed region.
    warmup = build_proteoform_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        DeterministicVerifier(),
    )
    if warmup.result.disposition is not ProteoformReleaseDisposition.RELEASED:
        raise AssertionError("warmup did not produce a released package")

    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        built = build_proteoform_release(
            fixture.request,
            fixture.artifacts,
            fixture.stages,
            DeterministicVerifier(),
        )
        elapsed = time.perf_counter_ns() - started
        if built.result.disposition is not ProteoformReleaseDisposition.RELEASED:
            raise AssertionError("benchmark call did not produce a released package")
        samples.append(elapsed)

    mean_ns = round(statistics.fmean(samples))
    median_ns = round(statistics.median(samples))
    p95_ns = _percentile(samples, 0.95)
    return {
        "module_id": MODULE_ID,
        "iterations": iterations,
        "mean_ns": mean_ns,
        "median_ns": median_ns,
        "p95_ns": p95_ns,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95_ns <= P95_BUDGET_NS,
        "samples_ns": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark(args.iterations)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
