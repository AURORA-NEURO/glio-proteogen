"""Representative M16-03 bounded fusion replay benchmark."""

from __future__ import annotations

import json
import statistics
import sys
import time

from tests.runtime.test_m16_03_engine import _request

from glio_proteogen.modules.c16_kinophos_object_consumer import (
    m16_03_fusion_aggregation_engine as m1603,
)

_ITERATIONS = 100


class _BenchmarkError(RuntimeError):
    pass


def main() -> int:
    request = _request()
    service = m1603.M1603Service()
    service.construct(request)
    samples: list[float] = []
    for _ in range(_ITERATIONS):
        started = time.perf_counter()
        result = service.construct(request)
        samples.append(time.perf_counter() - started)
        if result.status.value != "integrated":
            raise _BenchmarkError
    report = {
        "module_id": "GLIO-PROTEOGEN-M16-03",
        "iterations": _ITERATIONS,
        "mean_seconds": statistics.fmean(samples),
        "best_seconds": min(samples),
        "scope": "public attributable component-specific metadata replay only",
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
