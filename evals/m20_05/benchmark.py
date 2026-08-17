"""Locked microbenchmark wrapper for M20-05."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m20_05.fixture import build_request
from glio_proteogen.modules.c20_biomarker_panel.m20_05_workflow_presentation_service import (
    M2005Service,
)

_BUDGET_MEAN_NS = 500_000_000
_BUDGET_P95_NS = 750_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    """Measure deterministic in-process workspace presentation."""

    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M2005Service()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        service.present(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (len(ordered) * 95 + 99) // 100 - 1)]
    return {
        "module": "M20-05",
        "iterations": iterations,
        "mean_ns": round(statistics.fmean(samples)),
        "median_ns": round(statistics.median(samples)),
        "p95_ns": p95,
        "budget_mean_ns": _BUDGET_MEAN_NS,
        "budget_p95_ns": _BUDGET_P95_NS,
        "passed": statistics.fmean(samples) <= _BUDGET_MEAN_NS and p95 <= _BUDGET_P95_NS,
    }


def main() -> None:
    print(json.dumps(run_benchmark(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["main", "run_benchmark"]
