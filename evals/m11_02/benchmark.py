"""Small deterministic M11-02 benchmark receipt generator."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).parents[2]))

from evals.m11_02.support import request as _request
from glio_proteogen.modules.c11_protein_native_subtype.m11_02_context_subtype_stratifier import (
    M1102ContextEngine,
)

_BUDGET_MEAN_NS = 2_000_000_000
_BUDGET_P95_NS = 3_000_000_000


def measure(iterations: int = 10) -> dict[str, Any]:
    if isinstance(iterations, bool) or iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = M1102ContextEngine()
    request = _request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.stratify(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    return {
        "module_id": "GLIO-PROTEOGEN-M11-02",
        "iterations": iterations,
        "mean_ns": round(statistics.fmean(samples)),
        "median_ns": round(statistics.median(samples)),
        "p95_ns": ordered[p95_index],
        "budget_mean_ns": _BUDGET_MEAN_NS,
        "budget_p95_ns": _BUDGET_P95_NS,
        "passed": statistics.fmean(samples) < _BUDGET_MEAN_NS
        and ordered[p95_index] < _BUDGET_P95_NS,
    }


if __name__ == "__main__":
    import sys

    sys.stdout.write(json.dumps(measure(), indent=2, sort_keys=True) + "\n")
