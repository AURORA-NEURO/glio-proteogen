"""Locked microbenchmark wrapper for M20-02."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from statistics import median
from time import perf_counter_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m20_02.fixture import build_synthetic_request
from glio_proteogen.contracts.m20_02 import AlignProteinSubtypeSourcesRequest
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_02_cross_source_alignment_reconciliation import (  # noqa: E501
    M2002Engine,
)

RequestFactory = Callable[..., AlignProteinSubtypeSourcesRequest]


def run_benchmark(
    factory: RequestFactory = build_synthetic_request,
    iterations: int = 10,
) -> dict[str, object]:
    """Measure strict resolution without I/O or artifact traversal."""

    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = M2002Engine()
    request = factory()
    expected = engine.resolve(request)
    if expected.aligned_bundle is None:
        raise RuntimeError("benchmark fixture must be aligned")  # noqa: TRY003
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.resolve(request)
        samples.append(perf_counter_ns() - started)
        if result != expected:
            raise RuntimeError("benchmark result must be deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    mean_ns = sum(samples) / len(samples)
    p95_ns = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    budget_mean_ns = 500_000_000
    budget_p95_ns = 750_000_000
    return {
        "module": "GLIO-PROTEOGEN-M20-02",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean_ns,
        "median_ns": median(samples),
        "p95_ns": p95_ns,
        "budget_mean_ns": budget_mean_ns,
        "budget_p95_ns": budget_p95_ns,
        "request_digest": expected.request_digest,
        "result_digest": expected.result_digest,
        "passed": mean_ns <= budget_mean_ns and p95_ns <= budget_p95_ns,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the self-contained benchmark and optionally write its JSON report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_benchmark(iterations=args.iterations)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_benchmark"]
