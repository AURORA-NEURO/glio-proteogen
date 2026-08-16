"""Small deterministic M11-08 service-boundary benchmark."""

from __future__ import annotations

import json
import time
from math import ceil
from statistics import mean, median
from typing import Final

from evals.m11_08.run import AUTHORITY_LINES, AUTHORITY_SHA256, build_request
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_08_mechanism_evidence_dossier as m1108_runtime,
)

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def measure() -> dict[str, object]:
    service = m1108_runtime.M1108MechanismEvidenceDossierService()
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
        "module": "GLIO-PROTEOGEN-M11-08",
        "authority_sha256": AUTHORITY_SHA256,
        "authority_lines": AUTHORITY_LINES,
        "iterations": ITERATIONS,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "mean_ns": mean_ns,
        "median_ns": int(median(samples)),
        "p95_budget_ns": P95_BUDGET_NS,
        "p95_ns": p95,
        "samples_ns": samples,
        "timed_boundary": "M1108MechanismEvidenceDossierService.execute_only",
        "passed": mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


def main() -> None:
    print(json.dumps(measure(), indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["measure"]
