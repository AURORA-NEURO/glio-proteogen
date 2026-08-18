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

class _BenchmarkResultError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("benchmark request did not construct")


def main() -> int:
    request = _request()
    service = m1403.M1403Service()
    service.construct(request)
    samples: list[float] = []
    for _ in range(_ITERATIONS):
        started = time.perf_counter()
        result = service.construct(request)
        samples.append(time.perf_counter() - started)
        if result.status.value != "constructed":
            raise _BenchmarkResultError
    report = {
        "module_id": "GLIO-PROTEOGEN-M14-03",
        "iterations": _ITERATIONS,
        "mean_seconds": statistics.fmean(samples),
        "best_seconds": min(samples),
        "scope": "public caller-declared feature replay only",
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
