"""Locked M27-02 lineage benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from evals.m27_02.run import build_request
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service import M2702LineageResolver

_BUDGET_MEAN_NS = 500_000_000
_BUDGET_P95_NS = 750_000_000


class BenchmarkConfigurationError(ValueError):
    """The locked benchmark configuration is invalid."""


def run_benchmark(iterations: int = 10, output: Path | None = None) -> dict[str, object]:
    if iterations < 1:
        raise BenchmarkConfigurationError
    request = build_request()
    resolver = M2702LineageResolver()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        resolver.resolve(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, (len(ordered) * 95 + 99) // 100 - 1))]
    report: dict[str, object] = {
        "module_id": "GLIO-PROTEOGEN-M27-02",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": round(sum(samples) / len(samples), 2),
        "median_ns": ordered[len(ordered) // 2],
        "p95_ns": p95,
        "budget_mean_ns": _BUDGET_MEAN_NS,
        "budget_p95_ns": _BUDGET_P95_NS,
        "passed": sum(samples) / len(samples) <= _BUDGET_MEAN_NS and p95 <= _BUDGET_P95_NS,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json_bytes(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run_benchmark(arguments.iterations, arguments.output)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
