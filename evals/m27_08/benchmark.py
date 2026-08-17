"""M27-08 deterministic benchmark wrapper."""

# Benchmark scripts intentionally print machine-readable reports.
# ruff: noqa: T201, TRY003, PLR2004

from __future__ import annotations

import json
from statistics import mean
from time import perf_counter_ns

from evals.m27_08.fixture import build_request
from glio_proteogen.contracts.m27_08.canonical import canonical_request_digest
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import M2708Service


def main() -> int:
    service = M2708Service()
    request = build_request()
    service.execute(request)
    samples: list[int] = []
    first = None
    for _ in range(10):
        start = perf_counter_ns()
        result = service.execute(request)
        elapsed = perf_counter_ns() - start
        first = first or result.result_digest
        samples.append(elapsed)
        if result.result_digest != first:
            raise RuntimeError("non-deterministic result")
    samples_sorted = sorted(samples)
    p95 = samples_sorted[min(len(samples_sorted) - 1, int(len(samples_sorted) * 0.95))]
    payload = {
        "module_id": "GLIO-PROTEOGEN-M27-08",
        "iterations": 10,
        "warmup": True,
        "mean_ns": int(mean(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": 500_000_000,
        "p95_budget_ns": 750_000_000,
        "request_digest": canonical_request_digest(request),
        "result_digest": first,
        "deterministic": True,
        "passed": mean(samples) <= 500_000_000 and p95 <= 750_000_000,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
