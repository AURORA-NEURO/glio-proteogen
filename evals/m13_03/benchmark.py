"""M13-03 deterministic constructor benchmark."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m13_03.run import build_request
from glio_proteogen.modules.c11_protein_native_subtype import (
    m13_03_mechanistic_feature_constructor as m1303,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m13_03 import ConstructProteotypeMechanisticFeaturesRequest

construct_proteotype_mechanistic_features = m1303.construct_proteotype_mechanistic_features

_MEAN_BUDGET_NS = 2_000_000_000
_P95_BUDGET_NS = 3_000_000_000


def run_benchmark(
    iterations: int = 10,
    request: ConstructProteotypeMechanisticFeaturesRequest | None = None,
) -> dict[str, Any]:
    if isinstance(iterations, bool) or iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    candidate = request or build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        construct_proteotype_mechanistic_features(candidate)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, (len(ordered) * 95 + 99) // 100 - 1))]
    return {
        "module_id": "GLIO-PROTEOGEN-M13-03",
        "iterations": iterations,
        "mean_ns": round(statistics.fmean(samples)),
        "median_ns": round(statistics.median(samples)),
        "p95_ns": p95,
        "min_ns": min(samples),
        "max_ns": max(samples),
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "budgets_pass": statistics.fmean(samples) <= _MEAN_BUDGET_NS and p95 <= _P95_BUDGET_NS,
    }
