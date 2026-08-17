"""Locked microbenchmark wrapper for M26-06 security evaluation."""

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

from evals.m26_06.fixture import request_for
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control import (
    M2606SecurityService,
)

_MIN_ITERATIONS = 3


def benchmark(iterations: int = 10) -> dict[str, Any]:
    if iterations < _MIN_ITERATIONS:
        raise ValueError("benchmark requires at least three iterations")  # noqa: TRY003
    service = M2606SecurityService()
    request = request_for("benchmark")
    samples: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        result = service.execute(request)
        service.verify(result)
        samples.append(time.perf_counter_ns() - start)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    return {
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": int(statistics.mean(samples)),
        "median_ns": int(statistics.median(samples)),
        "p95_ns": ordered[p95_index],
        "budget_mean_ns": 500_000_000,
        "budget_p95_ns": 750_000_000,
    }


def main() -> None:
    print(json.dumps(benchmark(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
