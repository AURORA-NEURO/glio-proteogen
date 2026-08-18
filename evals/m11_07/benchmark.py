"""Small deterministic benchmark wrapper for M11-07."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from statistics import median

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m11_07.factory import build_request
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_07_plausibility_adjudicator as m1107,
)

M1107PlausibilityEngine = m1107.M1107PlausibilityEngine
_MEAN_BUDGET_NS = 2_000_000_000
_P95_BUDGET_NS = 3_000_000_000


class _BenchmarkConfigurationError(ValueError):
    def __init__(self) -> None:
        super().__init__("iterations must be positive")


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise _BenchmarkConfigurationError
    request = build_request()
    engine = M1107PlausibilityEngine()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.adjudicate(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    return {
        "module_id": "GLIO-PROTEOGEN-M11-07",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": sum(samples) // len(samples),
        "median_ns": int(median(samples)),
        "p95_ns": ordered[p95_index],
        "max_ns": max(samples),
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "within_budget": (
            sum(samples) // len(samples) <= _MEAN_BUDGET_NS and ordered[p95_index] <= _P95_BUDGET_NS
        ),
    }


def main() -> int:
    report = run_benchmark()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["within_budget"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_benchmark"]
