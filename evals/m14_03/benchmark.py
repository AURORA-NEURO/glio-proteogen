"""Representative M14-03 bounded replay benchmark."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.modules.c14_microenvironment_protein_deconvolution.test_m14_03_runtime import (
    _request,
)

from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_03_mechanistic_feature_constructor as m1403,
)

_ITERATIONS = 100
_MEAN_BUDGET_NS = 2_000_000_000
_P95_BUDGET_NS = 3_000_000_000


class _BenchmarkResultError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("benchmark request did not construct")


def run_benchmark(iterations: int = _ITERATIONS) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = _request()
    service = m1403.M1403Service()
    service.construct(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = service.construct(request)
        samples.append(time.perf_counter_ns() - started)
        if result.status.value != "constructed":
            raise _BenchmarkResultError
    ordered = sorted(samples)
    p95 = ordered[max(0, (iterations * 95 + 99) // 100 - 1)]
    average = int(statistics.mean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M14-03",
        "iterations": iterations,
        "mean_seconds": average / 1_000_000_000,
        "best_seconds": min(samples) / 1_000_000_000,
        "mean_ns": average,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "passed": average <= _MEAN_BUDGET_NS and p95 <= _P95_BUDGET_NS,
        "scope": "public caller-declared feature replay only",
    }


def main() -> int:
    report = run_benchmark()
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
