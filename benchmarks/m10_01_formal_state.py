"""Small benchmark wrapper for M10-01 deterministic execution."""

from __future__ import annotations

import json
import sys
from time import perf_counter_ns

from evals.m10_01.evaluate import make_request

from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema import (
    M1001FormalStateEngine,
)


def run(iterations: int = 10) -> dict[str, float | int]:
    """Run an explicit benchmark without pytest-benchmark dependencies."""

    if iterations < 1:
        raise ValueError
    engine = M1001FormalStateEngine()
    request = make_request()
    durations: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        engine.execute(request)
        durations.append(perf_counter_ns() - started)
    ordered = sorted(durations)
    p95_index = min(len(ordered) - 1, max(0, (95 * len(ordered) + 99) // 100 - 1))
    return {
        "iterations": iterations,
        "mean_ns": sum(durations) / len(durations),
        "median_ns": ordered[len(ordered) // 2],
        "p95_ns": ordered[p95_index],
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run(), indent=2, sort_keys=True) + "\n")
