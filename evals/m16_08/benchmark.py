"""M16-08 deterministic benchmark wrapper."""

# ruff: noqa: T201, TRY003

from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m16_08.run import build_scenario_request
from glio_proteogen.modules.c16_protein_rna_discordance.m16_08_translation_monitoring_rollback import (  # noqa: E501
    M1608TranslationMonitoringEngine,
)

MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    engine = M1608TranslationMonitoringEngine()
    request = build_scenario_request()
    engine.infer(request)
    samples: list[int] = []
    for _ in range(iterations):
        start = perf_counter_ns()
        engine.infer(request)
        samples.append(perf_counter_ns() - start)
    ordered = sorted(samples)
    p95 = ordered[max(0, (len(ordered) * 95 + 99) // 100 - 1)]
    average = int(mean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M16-08",
        "iterations": iterations,
        "mean_ns": average,
        "median_ns": int(median(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": average <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_benchmark(), sort_keys=True))
