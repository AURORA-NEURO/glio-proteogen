"""Small deterministic M16-06 queue replay benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.runtime.test_m16_06_queue import _request

from glio_proteogen.modules.c16_kinophos_object_consumer import M1606Engine


def main() -> dict[str, object]:
    engine = M1606Engine()
    request = _request()
    durations: list[float] = []
    for _ in range(100):
        started = perf_counter()
        engine.adjudicate(request)
        durations.append(perf_counter() - started)
    return {
        "module_id": "GLIO-PROTEOGEN-M16-06",
        "iterations": len(durations),
        "mean_seconds": sum(durations) / len(durations),
        "best_seconds": min(durations),
        "scope": "public typed reviewer queue metadata only",
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(main(), sort_keys=True) + "\n")
