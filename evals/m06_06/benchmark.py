"""Deterministic 25-call M06-06 provisional benchmark."""

from __future__ import annotations

import json
import statistics
import sys
import time
from typing import Any

from evals.m06_06.run import build_scenario
from glio_proteogen.contracts.m06_06 import (
    M0606_BENCHMARK_ITERATIONS,
    M0606_BENCHMARK_WARMUPS,
    M0606_MEAN_BUDGET_NS,
    M0606_P95_BUDGET_NS,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition import (
    decompose_protein_abundance_uncertainty,
)


def run_benchmark() -> dict[str, Any]:
    request = build_scenario().request
    for _ in range(M0606_BENCHMARK_WARMUPS):
        decompose_protein_abundance_uncertainty(request)
    samples: list[int] = []
    outputs = []
    for _ in range(M0606_BENCHMARK_ITERATIONS):
        started = time.perf_counter_ns()
        outputs.append(decompose_protein_abundance_uncertainty(request))
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    mean = int(statistics.fmean(samples))
    return {
        "module": "GLIO-PROTEOGEN-M06-06",
        "provisional_abi": True,
        "iterations": M0606_BENCHMARK_ITERATIONS,
        "warmups": M0606_BENCHMARK_WARMUPS,
        "mean_ns": mean,
        "p50_ns": ordered[len(ordered) // 2],
        "p95_ns": p95,
        "max_ns": max(ordered),
        "mean_budget_ns": M0606_MEAN_BUDGET_NS,
        "p95_budget_ns": M0606_P95_BUDGET_NS,
        "mean_budget_pass": mean <= M0606_MEAN_BUDGET_NS,
        "p95_budget_pass": p95 <= M0606_P95_BUDGET_NS,
        "deterministic_result_digest": outputs[0].result_digest,
        "all_digests_equal": len({item.result_digest for item in outputs}) == 1,
        "all_abstained": all(item.status.value == "abstained" for item in outputs),
    }


def main() -> None:
    sys.stdout.write(json.dumps(run_benchmark(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
