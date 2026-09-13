# ruff: noqa: T201, TRY003
"""Small repeatable M10-02 benchmark wrapper."""

from __future__ import annotations

import json
import time

from evals.m10_02.run import request

from glio_proteogen.contracts.m10_02 import RepresentationMissingness
from glio_proteogen.modules.c10_pathway_proteotype import (
    m10_02_representation_feature_constructor as m1002,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def run(iterations: int = 10) -> dict[str, bool | float | int | str]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    candidate = request(RepresentationMissingness.OBSERVED)
    durations: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = m1002.construct_protein_rna_representation(candidate)
        durations.append(time.perf_counter_ns() - started)
        if result.status.value != "constructed":
            raise RuntimeError("benchmark candidate unexpectedly abstained")
    ordered = sorted(durations)
    mean_ns = sum(durations) / iterations
    p95_ns = ordered[min(iterations - 1, max(0, int(iterations * 0.95) - 1))]
    return {
        "module_id": "GLIO-PROTEOGEN-M10-02",
        "iterations": iterations,
        "mean_ns": mean_ns,
        "median_ns": ordered[iterations // 2],
        "p95_ns": p95_ns,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95_ns <= P95_BUDGET_NS,
    }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
