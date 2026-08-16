"""Small deterministic benchmark wrapper for the M08-01 service."""

from __future__ import annotations

import statistics
import time

from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state import M0801Service

from .fixtures import request


def measure(iterations: int = 10) -> dict[str, float | int]:
    service = M0801Service()
    candidate = request()
    durations: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        service.execute(candidate)
        durations.append(time.perf_counter_ns() - start)
    ordered = sorted(durations)
    return {
        "iterations": iterations,
        "mean_ns": float(statistics.mean(durations)),
        "median_ns": float(statistics.median(durations)),
        "p95_ns": float(ordered[max(0, int(iterations * 0.95) - 1)]),
    }
