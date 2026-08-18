"""Deterministic provisional M10-06 benchmark wrapper."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m10_06.run import MODULE_ID, build_request
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_06_uncertainty_decomposition import (
    M1006UncertaintyDecompositionService,
)

MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M1006UncertaintyDecompositionService()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        service.execute(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    mean_ns = int(statistics.mean(samples))
    p95_ns = ordered[p95_index]
    return {
        "module_id": MODULE_ID,
        "iterations": iterations,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "mean_ns": mean_ns,
        "median_ns": int(statistics.median(samples)),
        "p95_budget_ns": P95_BUDGET_NS,
        "p95_ns": p95_ns,
        "samples_ns": samples,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95_ns <= P95_BUDGET_NS,
        "timed_boundary": "M1006UncertaintyDecompositionService.execute_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run_benchmark(arguments.iterations)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_benchmark"]
