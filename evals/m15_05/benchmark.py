"""Representative M15-05 bounded temporal replay benchmark."""

from __future__ import annotations

import json
import statistics
import sys
import time

from tests.runtime.test_m15_05_engine import _request

from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_05_longitudinal_evolution as m1505,
)

_ITERATIONS = 100


class _BenchmarkError(RuntimeError):
    pass


def main() -> int:
    request = _request()
    service = m1505.M1505Service()
    service.construct(request)
    samples: list[float] = []
    for _ in range(_ITERATIONS):
        started = time.perf_counter()
        result = service.construct(request)
        samples.append(time.perf_counter() - started)
        if result.status.value != "modeled":
            raise _BenchmarkError
    report = {
        "module_id": "GLIO-PROTEOGEN-M15-05",
        "iterations": _ITERATIONS,
        "mean_seconds": statistics.fmean(samples),
        "best_seconds": min(samples),
        "scope": "public ordered caller-declared metadata replay only",
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
