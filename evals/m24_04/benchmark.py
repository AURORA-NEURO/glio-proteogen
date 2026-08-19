"""Bounded M24-04 benchmark wrapper."""

from __future__ import annotations

import json
import sys
from statistics import mean, median
from time import perf_counter_ns

from glio_proteogen.modules.c21_reference_material import (
    m24_04_external_transport_evaluator as m2404,
)

from .fixture import request

_MAX_ITERATIONS = 1000


def run(iterations: int = 10) -> dict[str, float | int]:
    if not 1 <= iterations <= _MAX_ITERATIONS:
        raise ValueError("iterations must be between 1 and 1000")  # noqa: TRY003
    service = m2404.M2404Service()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        service.evaluate(request())
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    return {
        "iterations": iterations,
        "mean_ns": float(mean(samples)),
        "median_ns": float(median(samples)),
        "p95_ns": float(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]),
        "min_ns": float(ordered[0]),
        "max_ns": float(ordered[-1]),
    }


def main() -> None:
    sys.stdout.write(json.dumps(run(), sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
