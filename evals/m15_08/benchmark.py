"""Representative M15-08 bounded dossier replay benchmark."""

from __future__ import annotations

import json
import statistics
import sys
import time

from tests.runtime.test_m15_08_engine import _request

from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_08_mechanism_evidence_dossier as m1508,
)

_ITERATIONS = 100


class _BenchmarkError(RuntimeError):
    pass


def main() -> int:
    request = _request()
    service = m1508.M1508Service()
    service.construct(request)
    samples: list[float] = []
    for _ in range(_ITERATIONS):
        started = time.perf_counter()
        result = service.construct(request)
        samples.append(time.perf_counter() - started)
        if result.status.value != "ready":
            raise _BenchmarkError
    report = {
        "module_id": "GLIO-PROTEOGEN-M15-08",
        "iterations": _ITERATIONS,
        "mean_seconds": statistics.fmean(samples),
        "best_seconds": min(samples),
        "scope": "public caller-declared mechanism dossier metadata replay only",
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
