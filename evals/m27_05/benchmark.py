"""Deterministic M27-05 public-call benchmark with a warmup."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter_ns

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from glio_proteogen.contracts.m27_05.canonical import canonical_request_digest
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry import (
    M2705Service,
)

if __package__:
    from .fixture import build_request
else:
    from evals.m27_05.fixture import build_request

_ITERATIONS = 10
_MEAN_BUDGET_NS = 500_000_000
_P95_BUDGET_NS = 750_000_000


def run() -> dict[str, object]:
    """Run one untimed warmup and ten timed public calls."""

    service = M2705Service()
    request = build_request("m2705.request.benchmark")
    service.emit(request)
    samples: list[int] = []
    first_result_digest: str | None = None
    deterministic = True
    for _ in range(_ITERATIONS):
        started = perf_counter_ns()
        result = service.emit(request)
        samples.append(perf_counter_ns() - started)
        if first_result_digest is None:
            first_result_digest = result.result_digest
        elif result.result_digest != first_result_digest:
            deterministic = False
    ordered = sorted(samples)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    mean = sum(samples) // len(samples)
    report: dict[str, object] = {
        "module_id": "GLIO-PROTEOGEN-M27-05",
        "iterations": _ITERATIONS,
        "warmup": True,
        "request_digest": canonical_request_digest(request),
        "result_digest": first_result_digest,
        "request_bytes": len(request.model_dump_json().encode("utf-8")),
        "mean_ns": mean,
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "deterministic": deterministic,
    }
    report["passed"] = (
        deterministic and mean <= _MEAN_BUDGET_NS and p95 <= _P95_BUDGET_NS
    )
    return report


def main() -> int:
    report = run()
    print(json.dumps(report, sort_keys=True))  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run"]
