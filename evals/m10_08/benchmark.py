"""Small deterministic M10-08 service-boundary benchmark."""

from __future__ import annotations

import json
import time
from math import ceil
from statistics import mean, median
from typing import Final

from evals.m10_08.run import AUTHORITY_LINES, AUTHORITY_SHA256, build_request
from glio_proteogen.modules.c10_pathway_proteotype_factors import (
    m10_08_evidence_explanation_publisher as m1008_runtime,
)

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def measure() -> dict[str, object]:
    service = m1008_runtime.M1008EvidencePublisherService()
    request = build_request()
    service.execute(request)
    samples: list[int] = []
    for _ in range(ITERATIONS):
        started = time.perf_counter_ns()
        service.execute(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[max(0, ceil(0.95 * len(ordered)) - 1)]
    mean_ns = int(mean(samples))
    return {
        "module": "GLIO-PROTEOGEN-M10-08",
        "authority_sha256": AUTHORITY_SHA256,
        "authority_lines": AUTHORITY_LINES,
        "iterations": ITERATIONS,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "mean_ns": mean_ns,
        "median_ns": int(median(samples)),
        "p95_budget_ns": P95_BUDGET_NS,
        "p95_ns": p95,
        "samples_ns": samples,
        "timed_boundary": "M1008EvidencePublisherService.execute_only",
        "passed": mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


def main() -> None:
    print(json.dumps(measure(), indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["measure"]
