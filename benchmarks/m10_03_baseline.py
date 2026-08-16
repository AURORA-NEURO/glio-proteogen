"""Small deterministic M10-03 benchmark wrapper."""
# ruff: noqa: T201

from __future__ import annotations

from time import perf_counter_ns

from evals.m10_03.run import build_scenario_request

from glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator import (
    estimate_protein_rna_discordance_baseline,
)


def benchmark(iterations: int = 10) -> dict[str, int | float]:
    request = build_scenario_request()
    estimate_protein_rna_discordance_baseline(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        estimate_protein_rna_discordance_baseline(request)
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    return {
        "iterations": iterations,
        "mean_ns": sum(samples) / len(samples),
        "p95_ns": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "max_ns": max(samples),
    }


if __name__ == "__main__":
    print(benchmark())
