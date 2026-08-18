"""Deterministic M27-07 public-call benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter_ns

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from glio_proteogen.contracts.m27_07.canonical import canonical_request_digest
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control import M2707Service

if __package__:
    from .fixture import build_request
else:
    from evals.m27_07.fixture import build_request

_ITERATIONS = 10
_MEAN_BUDGET_NS = 500_000_000
_P95_BUDGET_NS = 750_000_000


def run() -> dict[str, object]:
    service = M2707Service()
    request = build_request("m2707.request.benchmark")
    service.execute(request)
    samples: list[int] = []
    digest: str | None = None
    deterministic = True
    for _ in range(_ITERATIONS):
        started = perf_counter_ns()
        result = service.execute(request)
        samples.append(perf_counter_ns() - started)
        if digest is None:
            digest = result.result_digest
        else:
            deterministic = deterministic and digest == result.result_digest
    ordered = sorted(samples)
    mean = sum(samples) // len(samples)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    return {
        "module_id": "GLIO-PROTEOGEN-M27-07",
        "iterations": _ITERATIONS,
        "warmup": True,
        "request_digest": canonical_request_digest(request),
        "result_digest": digest,
        "mean_ns": mean,
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "deterministic": deterministic,
        "passed": deterministic and mean <= _MEAN_BUDGET_NS and p95 <= _P95_BUDGET_NS,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, sort_keys=True))  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run"]
