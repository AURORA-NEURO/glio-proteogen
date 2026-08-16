"""Bounded M07-07 benchmark wrapper with fixture construction outside timing."""

from __future__ import annotations

import json
from statistics import mean, median
from time import perf_counter_ns

from glio_proteogen.modules.c07_copy_number_dosage.m07_07_calibration_selective_prediction import (
    M0707Service,
)

from .fixtures import request

_MAX_MEAN_NS = 2_000_000_000
_MAX_P95_NS = 3_000_000_000


def benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations <= 0:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    active_request = request()
    service = M0707Service()
    service.execute(active_request)
    timings: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = service.execute(active_request)
        timings.append(perf_counter_ns() - started)
        if result.status.value != "calibrated":
            raise AssertionError("benchmark fixture did not calibrate")  # noqa: TRY003
    ordered = sorted(timings)
    p95 = ordered[max(0, (len(ordered) * 95 + 99) // 100 - 1)]
    return {
        "module_id": "GLIO-PROTEOGEN-M07-07",
        "iterations": iterations,
        "mean_ns": int(mean(timings)),
        "median_ns": int(median(timings)),
        "p95_ns": p95,
        "max_mean_ns": _MAX_MEAN_NS,
        "max_p95_ns": _MAX_P95_NS,
        "passed": mean(timings) <= _MAX_MEAN_NS and p95 <= _MAX_P95_NS,
        "timings_ns": timings,
    }


def main() -> None:
    print(json.dumps(benchmark(), indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["benchmark", "main"]
