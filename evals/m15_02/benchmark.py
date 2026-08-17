"""Representative M15-02 bounded context replay benchmark."""

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

from tests.runtime.test_m15_02_engine import _request

from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_02_context_subtype_stratifier as m1502,
)

_ITERATIONS = 100


class _BenchmarkError(RuntimeError):
    pass


def main() -> int:
    request = _request()
    service = m1502.M1502Service()
    service.construct(request)
    samples: list[float] = []
    for _ in range(_ITERATIONS):
        started = time.perf_counter()
        result = service.construct(request)
        samples.append(time.perf_counter() - started)
        if result.status.value != "stratified":
            raise _BenchmarkError
    report = {
        "module_id": "GLIO-PROTEOGEN-M15-02",
        "iterations": _ITERATIONS,
        "mean_seconds": statistics.fmean(samples),
        "best_seconds": min(samples),
        "scope": "public caller-declared context and mechanism replay only",
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
