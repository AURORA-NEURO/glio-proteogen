"""Locked M26-03 deterministic execution benchmark."""

# The benchmark's assertion and console output are deliberate evidence-tool
# behavior, not library runtime behavior.
# ruff: noqa: E501,S101,TRY003,T201,PLR2004

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m26_03.fixture import build_request
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator import (
    M2603Engine,
)


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    """Measure full request validation, execution, and package construction."""

    if iterations < 1:
        raise ValueError("iterations must be positive")
    request = build_request()
    engine = M2603Engine()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.execute(request)
        elapsed = perf_counter_ns() - started
        assert result.execution_record is not None
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    return {
        "module_id": "GLIO-PROTEOGEN-M26-03",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": int(mean(samples)),
        "median_ns": int(median(samples)),
        "p95_ns": p95,
        "budgets_ns": {"mean_max": 500_000_000, "p95_max": 750_000_000},
        "fixture_digest": sha256_digest(request),
        "passed": mean(samples) <= 500_000_000 and p95 <= 750_000_000,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run_benchmark(args.iterations), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()


__all__ = ["main", "run_benchmark"]
